"""Layer 2 of D80: forward-only SQL migrations from `pits/warehouse/migrations/NNNN_<name>.sql`.

- Strict discovery: names `NNNN_<snake_name>.sql`, versions 1..N without gaps or duplicates.
- Each file runs in its own transaction, under `SET LOCAL ROLE <owner>` and a transaction
  advisory lock; the applied file's sha256 is stored in `ops.schema_migration`.
- A changed sha256 (or name) for an applied version is a permanent error: migrations are
  never edited, only added.
- Files may use the placeholders `{{owner_role}}`, `{{loader_role}}`, `{{reader_role}}`,
  `{{transformer_role}}`
  (substituted as quoted identifiers) so that grants work with the real roles and with the
  per-session roles used by tests. The recorded sha256 is over the raw file bytes.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable

import psycopg
from psycopg import sql

from pits.warehouse.bootstrap import bootstrap_locked, run_lock
from pits.warehouse.connection import connect
from pits.warehouse.errors import (
    WarehouseError,
    WarehousePermanentError,
    WarehouseTransientError,
    to_warehouse_error,
)
from pits.warehouse.settings import Profile, RoleNames, WarehouseSettings

MIGRATE_LOCK_KEY = 0x5049545302  # advisory lock key inside the warehouse database
LOCK_TIMEOUT = "10s"
STATEMENT_TIMEOUT = "10min"

_FILE_RE = re.compile(r"^(\d{4})_([a-z][a-z0-9_]*)\.sql$")
_IGNORED = frozenset({".gitkeep", "__init__.py", "__pycache__"})


class MigrationError(WarehousePermanentError):
    """Invalid migration set or drift against what is recorded as applied."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str
    sha256: str

    @property
    def filename(self) -> str:
        return f"{self.version:04d}_{self.name}.sql"


@dataclass(frozen=True)
class MigrateResult:
    applied: int
    skipped: int


def default_source() -> Traversable:
    return files("pits.warehouse") / "migrations"


def discover_migrations(source: Traversable | None = None) -> list[Migration]:
    """Read and validate the migration files; raises MigrationError on any irregularity."""
    source = source if source is not None else default_source()
    found: list[Migration] = []
    for entry in source.iterdir():
        if entry.name in _IGNORED:
            continue
        match = _FILE_RE.match(entry.name)
        if match is None or not entry.is_file():
            raise MigrationError(f"Invalid migration entry name: {entry.name!r}")
        raw = entry.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise MigrationError(f"Migration {entry.name} is not valid UTF-8") from None
        found.append(
            Migration(
                version=int(match.group(1)),
                name=match.group(2),
                sql=text,
                sha256=hashlib.sha256(raw).hexdigest(),
            )
        )
    found.sort(key=lambda m: m.version)
    for expected, migration in enumerate(found, start=1):
        if migration.version == expected:
            continue
        if expected > 1 and migration.version == found[expected - 2].version:
            raise MigrationError(f"Duplicate migration version {migration.version:04d}")
        raise MigrationError(
            f"Migration versions must be contiguous from 0001: expected {expected:04d}, "
            f"found {migration.version:04d}"
        )
    return found


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def render(migration: Migration, roles: RoleNames) -> str:
    """Substitute role placeholders with quoted identifiers."""
    return (
        migration.sql.replace("{{owner_role}}", _quote(roles.owner))
        .replace("{{loader_role}}", _quote(roles.loader))
        .replace("{{reader_role}}", _quote(roles.reader))
        .replace("{{transformer_role}}", _quote(roles.transformer))
    )


def _read_applied(conn: psycopg.Connection) -> dict[int, tuple[str, str]]:
    try:
        rows = conn.execute("SELECT version, name, sha256 FROM ops.schema_migration").fetchall()
    except psycopg.errors.UndefinedTable:
        conn.rollback()
        raise MigrationError("ops.schema_migration is missing; run the bootstrap first") from None
    conn.commit()
    return {version: (name, sha) for version, name, sha in rows}


def _check_applied(applied: dict[int, tuple[str, str]], migrations: list[Migration]) -> None:
    by_version = {m.version: m for m in migrations}
    for version in sorted(applied):
        name, sha = applied[version]
        migration = by_version.get(version)
        if migration is None:
            raise MigrationError(f"Applied migration {version:04d}_{name} is not in the package")
        if migration.name != name or migration.sha256 != sha:
            raise MigrationError(
                f"Migration {migration.filename} changed after being applied "
                "(migrations are forward-only; add a new file instead)"
            )
    if applied and sorted(applied) != list(range(1, max(applied) + 1)):
        raise MigrationError("Applied migrations are not a contiguous prefix")


def apply_migrations(
    conn: psycopg.Connection, migrations: list[Migration], roles: RoleNames
) -> MigrateResult:
    """Apply pending migrations on an admin connection (autocommit off)."""
    applied = _read_applied(conn)
    _check_applied(applied, migrations)
    skipped = len(applied)
    count = 0
    for migration in migrations:
        if migration.version in applied:
            continue
        try:
            locked = conn.execute(
                "SELECT pg_try_advisory_xact_lock(%s)", (MIGRATE_LOCK_KEY,)
            ).fetchone()
            if not locked or not locked[0]:
                raise WarehouseTransientError("Another migration run holds the advisory lock")
            # A concurrent runner may have applied it before we got the lock.
            row = conn.execute(
                "SELECT name, sha256 FROM ops.schema_migration WHERE version = %s",
                (migration.version,),
            ).fetchone()
            if row is not None:
                if (row[0], row[1]) != (migration.name, migration.sha256):
                    raise MigrationError(f"Migration {migration.filename} changed concurrently")
                conn.commit()
                skipped += 1
                continue
            conn.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
            conn.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
            conn.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(roles.owner)))
            conn.execute(render(migration, roles).encode())
            conn.execute(
                "INSERT INTO ops.schema_migration (version, name, sha256) VALUES (%s, %s, %s)",
                (migration.version, migration.name, migration.sha256),
            )
            conn.commit()
            count += 1
        except WarehouseError:
            conn.rollback()
            raise
        except psycopg.Error as exc:
            conn.rollback()
            raise to_warehouse_error(exc, f"migration {migration.filename}") from None
    return MigrateResult(applied=count, skipped=skipped)


def run_migrate(settings: WarehouseSettings, source: Traversable | None = None) -> MigrateResult:
    """Bootstrap (layer 1) then apply pending migrations (layer 2) as the admin profile.

    One run-wide session lock (see `run_lock`) covers both layers; if it is busy the run
    fails as transient before the bootstrap touches anything. The per-migration transaction
    lock inside the warehouse database stays as a second line of defense.
    """
    migrations = discover_migrations(source)  # fail before touching the server
    with run_lock(settings) as maintenance:
        bootstrap_locked(maintenance, settings)
        conn = connect(settings, Profile.ADMIN, autocommit=False, application_name="pits-migrate")
        try:
            return apply_migrations(conn, migrations, settings.roles)
        finally:
            conn.close()

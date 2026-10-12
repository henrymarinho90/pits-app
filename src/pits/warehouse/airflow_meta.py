"""D93: isolated metadata database and role for Airflow, created by the admin by hand.

`pits db init-airflow-meta` creates (idempotently) the database `airflow_meta` and the LOGIN role
`airflow_meta` in the same Postgres instance as the warehouse. The role owns only that database,
has the same least-privilege attributes as the warehouse roles and has no access to the
warehouse: `REVOKE ALL ON DATABASE <warehouse> FROM PUBLIC` (D79 bootstrap) leaves CONNECT to the
three pits roles only, and here `airflow_meta` is revoked from PUBLIC too, so neither side can
connect to the other one.

The password (`AIRFLOW_METADB_PASSWORD`) is sent as a SCRAM-SHA-256 verifier computed in the
client (same helper as the D79/D86 bootstrap), so the plaintext never appears in SQL text or logs.
The whole run holds `RUN_LOCK_KEY` (the same session lock as `pits db migrate`) on the admin
connection to the maintenance database, so it never overlaps a migrate.

Re-running only re-asserts the same state: "created" means the role or the database did not exist,
"unchanged" means both did (attributes, owner, privileges and the password verifier are
re-asserted anyway, as the bootstrap does).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

import psycopg
from psycopg import errors as pgerr
from psycopg import sql

from pits.warehouse.bootstrap import run_lock, scram_verifier
from pits.warehouse.errors import WarehouseConfigError, WarehouseError, to_warehouse_error
from pits.warehouse.settings import MIN_PASSWORD_LENGTH, WarehouseSettings

AIRFLOW_META_NAME = "airflow_meta"
PASSWORD_ENV = "AIRFLOW_METADB_PASSWORD"
_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
# Same least-privilege attributes as the warehouse roles (bootstrap._ATTRS).
_ATTRS = "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS"


@dataclass(frozen=True)
class AirflowMetaResult:
    database: str
    role: str
    created: bool

    @property
    def status(self) -> str:
        return "created" if self.created else "unchanged"


def load_metadb_password(env: Mapping[str, str]) -> str:
    """Password of the airflow_meta role; error messages never include the value."""
    value = env.get(PASSWORD_ENV, "")
    if not value.strip():
        raise WarehouseConfigError(f"Missing required environment variable: {PASSWORD_ENV}")
    if value != value.strip():
        raise WarehouseConfigError(f"{PASSWORD_ENV} must not have leading or trailing whitespace")
    if len(value) < MIN_PASSWORD_LENGTH:
        raise WarehouseConfigError(
            f"{PASSWORD_ENV} must be at least {MIN_PASSWORD_LENGTH} characters"
        )
    return value


def _check_name(name: str, what: str) -> None:
    if not _IDENT_RE.match(name):
        raise WarehouseConfigError(f"{what} must match ^[a-z][a-z0-9_]{{0,62}}$")


def _upsert_role(conn: psycopg.Connection, role: str, password: str) -> bool:
    """CREATE or ALTER the LOGIN role; True when it was created."""
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
    conn.execute(
        sql.SQL("{verb} ROLE {name} LOGIN {attrs} PASSWORD {password}").format(
            verb=sql.SQL("ALTER" if exists else "CREATE"),
            name=sql.Identifier(role),
            attrs=sql.SQL(_ATTRS),
            password=sql.Literal(scram_verifier(conn, role, password)),
        )
    )
    return exists is None


def _upsert_database(conn: psycopg.Connection, dbname: str, role: str) -> bool:
    """CREATE DATABASE needs autocommit; True when it was created."""
    db, owner = sql.Identifier(dbname), sql.Identifier(role)
    exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)).fetchone()
    created = exists is None
    if created:
        try:
            conn.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(db, owner))
        except pgerr.DuplicateDatabase:
            created = False  # lost a race; the ALTER below normalizes the owner
    conn.execute(sql.SQL("ALTER DATABASE {} OWNER TO {}").format(db, owner))
    # Nobody but the owner (and superusers) may connect: not even the pits roles.
    conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(db))
    return created


def init_airflow_meta(
    settings: WarehouseSettings,
    password: str,
    *,
    dbname: str = AIRFLOW_META_NAME,
    role: str = AIRFLOW_META_NAME,
) -> AirflowMetaResult:
    """Idempotent role + database creation under the run lock; raises typed warehouse errors.

    `dbname` and `role` are injectable only so that tests use unique names; the CLI uses the
    defaults. `settings` must carry the admin profile.
    """
    _check_name(dbname, "Airflow metadata database name")
    _check_name(role, "Airflow metadata role name")
    with run_lock(settings) as maintenance:
        try:
            role_created = _upsert_role(maintenance, role, password)
            db_created = _upsert_database(maintenance, dbname, role)
        except WarehouseError:
            raise
        except psycopg.Error as exc:
            raise to_warehouse_error(exc, "init-airflow-meta") from None
    return AirflowMetaResult(database=dbname, role=role, created=role_created or db_created)

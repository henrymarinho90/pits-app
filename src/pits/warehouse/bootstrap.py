"""Layer 1 of D80: idempotent cluster/database bootstrap run as the admin (superuser) profile.

Creates roles, the warehouse database, schemas `ops`, `landing` and the dbt schemas (D86),
the baseline privileges and `ops.schema_migration`. Re-running only re-asserts the same state
(and rotates the password verifiers). Table-level grants belong to the SQL migrations (layer 2).

Role passwords are sent as SCRAM-SHA-256 verifiers computed in the client
(`PGconn.encrypt_password`), so the plaintext never appears in SQL text, server logs or
`pg_stat_activity`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg import errors as pgerr
from psycopg import sql

from pits.warehouse.connection import connect
from pits.warehouse.errors import (
    WarehouseError,
    WarehousePermanentError,
    WarehouseTransientError,
    to_warehouse_error,
)
from pits.warehouse.locks import RUN_LOCK_KEY as RUN_LOCK_KEY
from pits.warehouse.locks import WAREHOUSE_LOCK_KEY
from pits.warehouse.settings import Profile, WarehouseSettings

MAINTENANCE_DB = "postgres"
LOCK_TIMEOUT = "10s"
STATEMENT_TIMEOUT = "10min"
SCHEMAS = ("ops", "landing")
# The bootstrap creates these schemas (owner pits_owner, so only the owner can drop or rename
# them); dbt, as pits_transformer, only builds objects inside them (D86).
DBT_SCHEMAS = ("staging", "intermediate", "marts")

# Least privilege: no superuser/createdb/createrole/replication/bypassrls; NOINHERIT because
# the roles have no memberships and must never gain privileges implicitly.
_ATTRS = "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS"


def scram_verifier(conn: psycopg.Connection, user: str, password: str) -> str:
    """SCRAM-SHA-256 verifier computed client-side (libpq PQencryptPasswordConn)."""
    verifier = conn.pgconn.encrypt_password(password.encode(), user.encode(), b"scram-sha-256")
    text = verifier.decode()
    if not text.startswith("SCRAM-SHA-256$"):
        raise WarehousePermanentError("Unexpected password verifier format")
    return text


def _upsert_role(conn: psycopg.Connection, name: str, *, login: bool, password: str | None) -> None:
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,)).fetchone()
    verb = "ALTER" if exists else "CREATE"
    password_sql = (
        sql.SQL("PASSWORD {}").format(sql.Literal(scram_verifier(conn, name, password)))
        if password is not None
        else sql.SQL("PASSWORD NULL")
    )
    conn.execute(
        sql.SQL("{verb} ROLE {name} {login} {attrs} {password}").format(
            verb=sql.SQL(verb),
            name=sql.Identifier(name),
            login=sql.SQL("LOGIN" if login else "NOLOGIN"),
            attrs=sql.SQL(_ATTRS),
            password=password_sql,
        )
    )


def _bootstrap_roles(conn: psycopg.Connection, settings: WarehouseSettings) -> None:
    roles = settings.roles
    _, loader_password = settings.credentials(Profile.LOADER)
    _, reader_password = settings.credentials(Profile.READER)
    _, transformer_password = settings.credentials(Profile.TRANSFORMER)
    _upsert_role(conn, roles.owner, login=False, password=None)
    _upsert_role(conn, roles.loader, login=True, password=loader_password)
    _upsert_role(conn, roles.reader, login=True, password=reader_password)
    _upsert_role(conn, roles.transformer, login=True, password=transformer_password)


def _bootstrap_database(conn: psycopg.Connection, settings: WarehouseSettings) -> None:
    """CREATE DATABASE cannot run inside a transaction, so `conn` must be in autocommit."""
    db, owner = sql.Identifier(settings.dbname), sql.Identifier(settings.roles.owner)
    exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (settings.dbname,))
    if exists.fetchone() is None:
        try:
            conn.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(db, owner))
        except pgerr.DuplicateDatabase:
            pass  # lost a race with another bootstrap; the ALTER below normalizes the owner
    conn.execute(sql.SQL("ALTER DATABASE {} OWNER TO {}").format(db, owner))


def _bootstrap_objects(conn: psycopg.Connection, settings: WarehouseSettings) -> None:
    """Runs in one transaction inside the warehouse database."""
    r = settings.roles
    owner, loader, reader, transformer = (
        sql.Identifier(n) for n in (r.owner, r.loader, r.reader, r.transformer)
    )
    db = sql.Identifier(settings.dbname)
    run = conn.execute

    run(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(db))
    run(sql.SQL("GRANT CONNECT, TEMPORARY ON DATABASE {} TO {}").format(db, loader))
    run(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(db, reader, transformer))
    run("REVOKE ALL ON SCHEMA public FROM PUBLIC")

    for schema in SCHEMAS:
        name = sql.Identifier(schema)
        run(sql.SQL("CREATE SCHEMA IF NOT EXISTS {} AUTHORIZATION {}").format(name, owner))
        run(sql.SQL("ALTER SCHEMA {} OWNER TO {}").format(name, owner))
        run(sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(name))
        run(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}, {}").format(name, loader, reader))
    # dbt schemas: the transformer builds there (USAGE+CREATE); the reader only sees marts (D86).
    for schema in DBT_SCHEMAS:
        name = sql.Identifier(schema)
        run(sql.SQL("CREATE SCHEMA IF NOT EXISTS {} AUTHORIZATION {}").format(name, owner))
        run(sql.SQL("ALTER SCHEMA {} OWNER TO {}").format(name, owner))
        run(sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC, {}").format(name, reader))
        run(sql.SQL("GRANT USAGE, CREATE ON SCHEMA {} TO {}").format(name, transformer))
    run(sql.SQL("GRANT USAGE ON SCHEMA marts TO {}").format(reader))
    run(sql.SQL("GRANT USAGE ON SCHEMA landing, ops TO {}").format(transformer))
    # Tables dbt creates in marts become readable by the reader (D86).
    run(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA marts GRANT SELECT ON TABLES TO {}"
        ).format(transformer, reader)
    )
    # Tables the owner creates in landing become readable by the transformer and reader.
    run(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA landing GRANT SELECT ON TABLES TO {}"
        ).format(owner, transformer)
    )
    # Tables the owner creates in landing become readable by the reader (D79).
    run(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA landing GRANT SELECT ON TABLES TO {}"
        ).format(owner, reader)
    )

    # ops.schema_migration is created as the owner so the owner keeps owning everything.
    run(sql.SQL("SET LOCAL ROLE {}").format(owner))
    run(
        """
        CREATE TABLE IF NOT EXISTS ops.schema_migration (
            version    integer     PRIMARY KEY CHECK (version > 0),
            name       text        NOT NULL CHECK (name ~ '^[a-z][a-z0-9_]*$'),
            sha256     text        NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
            applied_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    run("RESET ROLE")


def _set_timeouts(conn: psycopg.Connection) -> None:
    conn.execute(sql.SQL("SET lock_timeout = {}").format(sql.Literal(LOCK_TIMEOUT)))
    conn.execute(sql.SQL("SET statement_timeout = {}").format(sql.Literal(STATEMENT_TIMEOUT)))


@contextmanager
def run_lock(settings: WarehouseSettings) -> Iterator[psycopg.Connection]:
    """Hold the run-wide advisory lock for the whole `pits db migrate` run.

    The lock is a session lock taken on an admin connection to the maintenance database
    (`postgres`), which exists in every cluster and is the same one every code path uses
    (bootstrap alone and bootstrap + migrations). The connection stays open (autocommit) for
    the whole run and is yielded for the cluster-level bootstrap steps. Busy lock ->
    WarehouseTransientError before anything is executed.
    """
    maintenance = connect(settings, Profile.ADMIN, dbname=MAINTENANCE_DB, autocommit=True)
    try:
        try:
            _set_timeouts(maintenance)
            locked = maintenance.execute(
                "SELECT pg_try_advisory_lock(%s)", (RUN_LOCK_KEY,)
            ).fetchone()
        except psycopg.Error as exc:
            raise to_warehouse_error(exc, "run lock") from None
        if not locked or not locked[0]:
            raise WarehouseTransientError("Another pits db run holds the advisory lock")
        try:
            yield maintenance
        finally:
            try:
                maintenance.execute("SELECT pg_advisory_unlock(%s)", (RUN_LOCK_KEY,))
            except psycopg.Error:
                # Never mask the original error; closing the session releases the lock anyway.
                pass
    finally:
        maintenance.close()


@contextmanager
def warehouse_lock(settings: WarehouseSettings) -> Iterator[None]:
    """Hold the warehouse write lock (D90) on a separate admin connection to the warehouse DB.

    Session lock with `WAREHOUSE_LOCK_KEY`, the same key the load and the transform take, so
    a migration never overlaps them. The database must already exist. Busy lock ->
    WarehouseTransientError before anything is written.
    """
    conn = connect(settings, Profile.ADMIN, autocommit=True, application_name="pits-migrate-lock")
    try:
        try:
            locked = conn.execute("SELECT pg_try_advisory_lock(%s)", (WAREHOUSE_LOCK_KEY,))
            row = locked.fetchone()
        except psycopg.Error as exc:
            raise to_warehouse_error(exc, "warehouse lock") from None
        if not row or not row[0]:
            raise WarehouseTransientError("Another warehouse writer holds the lock")
        try:
            yield
        finally:
            try:
                conn.execute("SELECT pg_advisory_unlock(%s)", (WAREHOUSE_LOCK_KEY,))
            except psycopg.Error:
                # Never mask the original error; closing the session releases the lock anyway.
                pass
    finally:
        conn.close()


@contextmanager
def bootstrap_locked(
    maintenance: psycopg.Connection, settings: WarehouseSettings
) -> Iterator[None]:
    """Bootstrap steps; the caller must already hold `run_lock` on `maintenance`.

    Creates roles and the database, then takes `warehouse_lock` and writes the objects. The
    warehouse lock stays held while the caller's `with` body runs (e.g. the migrations) and is
    released on exit.
    """
    try:
        _bootstrap_roles(maintenance, settings)
        _bootstrap_database(maintenance, settings)
    except WarehouseError:
        raise
    except psycopg.Error as exc:
        raise to_warehouse_error(exc, "bootstrap") from None
    with warehouse_lock(settings):
        try:
            target = connect(settings, Profile.ADMIN, autocommit=False)
            try:
                _set_timeouts(target)
                _bootstrap_objects(target, settings)
                target.commit()
            finally:
                target.close()
        except WarehouseError:
            raise
        except psycopg.Error as exc:
            raise to_warehouse_error(exc, "bootstrap") from None
        yield


def bootstrap(settings: WarehouseSettings) -> None:
    """Idempotent bootstrap under the run lock; raises typed warehouse errors."""
    with run_lock(settings) as maintenance, bootstrap_locked(maintenance, settings):
        pass

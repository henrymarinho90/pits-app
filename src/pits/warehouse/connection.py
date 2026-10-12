"""Postgres connections with explicit parameters and a post-connect identity check.

libpq fills any parameter we do not pass from PG* environment variables (and from
PGSERVICE / pg_service.conf). Mitigation: host, port, dbname, user, password, timeouts,
application_name, sslmode, client_encoding and options (TimeZone=UTC, DateStyle=ISO) are
always passed explicitly (explicit parameters win over PG* variables). Variables that
cannot be neutralized that way (PGSERVICE, PGSERVICEFILE, PGSYSCONFDIR, PGHOSTADDR,
PGOPTIONS, PGTARGETSESSIONATTRS, PGPASSFILE) are rejected if present in the environment.

Connection failures: psycopg 3.3 raises OperationalError WITHOUT sqlstate when connecting
fails, even for server rejections (28P01, 28000, 3D000). We therefore classify by how far
the handshake got: if the client already sent/needed a password (pgconn.used_password or
needs_password) the server answered, so the failure is permanent. Transient (retryable):
connection refused, timeout, DNS/socket errors and "starting up" (57P03), all of which
happen before authentication. Rejections that occur before any password is exchanged
(e.g. 28000 under trust/pg_hba reject) cannot be told apart and are treated as transient.
Known limitation (opposite direction): a transient server refusal sent AFTER authentication,
such as 53300 "remaining connection slots are reserved ...", also arrives without sqlstate on
connect and with the password already used, so it is classified permanent (exit 1) although a
retry might succeed.

Typed errors are raised outside the `except` blocks (so `__context__` is None): the original
psycopg error references the pgconn, which holds the password. The CLIs print only str(exc).
"""

from __future__ import annotations

import os
from collections.abc import Mapping

import psycopg
from psycopg.conninfo import make_conninfo

from pits.warehouse.errors import (
    WarehouseConfigError,
    WarehouseError,
    WarehousePermanentError,
    describe_error,
    to_warehouse_error,
)
from pits.warehouse.settings import Profile, WarehouseSettings

EXPECTED_MAJOR_VERSION = 17
CONNECT_TIMEOUT_SECONDS = 10
DEFAULT_APPLICATION_NAME = "pits"

# Not neutralized by passing an explicit parameter, so they are refused instead.
_FORBIDDEN_ENV = (
    "PGSERVICE",
    "PGSERVICEFILE",
    "PGSYSCONFDIR",
    "PGHOSTADDR",
    "PGOPTIONS",
    "PGTARGETSESSIONATTRS",
    "PGPASSFILE",
)


def check_environment(env: Mapping[str, str] | None = None) -> None:
    """Reject PG* variables libpq would otherwise honor behind our back."""
    env = os.environ if env is None else env
    present = [name for name in _FORBIDDEN_ENV if env.get(name)]
    if present:
        raise WarehouseConfigError(
            "Unset these libpq environment variables first: " + ", ".join(present)
        )


def build_conninfo(
    settings: WarehouseSettings,
    profile: Profile,
    *,
    dbname: str | None = None,
    application_name: str = DEFAULT_APPLICATION_NAME,
) -> str:
    """Conninfo string from explicit parts; contains the password, so never log it."""
    user, password = settings.credentials(profile)
    return make_conninfo(
        host=settings.host,
        port=settings.port,
        dbname=dbname or settings.dbname,
        user=user,
        password=password,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        application_name=application_name,
        sslmode="disable",  # loopback or `postgres` only (D91, enforced by settings)
        client_encoding="UTF8",
        options="-c TimeZone=UTC -c DateStyle=ISO",
    )


def _authenticated(exc: psycopg.Error) -> bool:
    """True if the failed connection got far enough for the server to judge credentials."""
    pgconn = exc.pgconn
    if pgconn is None:
        return False
    for attr in ("used_password", "needs_password"):
        try:
            if getattr(pgconn, attr):
                return True
        except (psycopg.NotSupportedError, psycopg.OperationalError):
            continue  # libpq too old for this attribute or connection already finished
    return False


def classify_connect_error(exc: psycopg.Error, context: str) -> WarehouseError:
    """Typed error for a failed psycopg.connect (see module docstring for the rules)."""
    if exc.sqlstate is None and _authenticated(exc):
        return WarehousePermanentError(f"{context}: {describe_error(exc)} (server rejected login)")
    return to_warehouse_error(exc, context)


def verify_server(conn: psycopg.Connection, expected_dbname: str) -> None:
    """Fail permanently unless the server is Postgres 17 and the database is the expected one."""
    row = conn.execute(
        "SELECT current_setting('server_version_num')::int, current_database()"
    ).fetchone()
    if row is None:  # pragma: no cover - SELECT without FROM always returns a row
        raise WarehousePermanentError("Server identity check returned no row")
    version_num, current_db = row
    if version_num // 10000 != EXPECTED_MAJOR_VERSION:
        raise WarehousePermanentError(
            f"Unsupported Postgres major version {version_num // 10000}; "
            f"expected {EXPECTED_MAJOR_VERSION}"
        )
    if current_db != expected_dbname:
        raise WarehousePermanentError("Connected to an unexpected database")


def connect(
    settings: WarehouseSettings,
    profile: Profile,
    *,
    dbname: str | None = None,
    autocommit: bool = False,
    application_name: str = DEFAULT_APPLICATION_NAME,
    env: Mapping[str, str] | None = None,
) -> psycopg.Connection:
    """Open a verified connection; errors are typed (transient/permanent) and secret-free."""
    check_environment(env)
    target_db = dbname or settings.dbname
    conninfo = build_conninfo(
        settings, profile, dbname=target_db, application_name=application_name
    )
    # The typed error is raised OUTSIDE the except blocks so that its __context__ is None:
    # the original psycopg error references the pgconn, which holds the password.
    failure: WarehouseError | None = None
    conn: psycopg.Connection | None = None
    try:
        conn = psycopg.connect(conninfo, autocommit=True)
    except psycopg.Error as exc:
        failure = classify_connect_error(exc, f"connect as {profile.value}")
    if failure is not None or conn is None:
        raise failure or WarehousePermanentError("connect failed")
    try:
        verify_server(conn, target_db)
        conn.autocommit = autocommit
    except psycopg.Error as exc:
        failure = to_warehouse_error(exc, "server identity check")
    except Exception:
        conn.close()
        raise
    if failure is not None:
        conn.close()
        raise failure
    return conn

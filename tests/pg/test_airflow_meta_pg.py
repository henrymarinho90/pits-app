"""D93: `init_airflow_meta` against a real Postgres 17 (unique names per test, cleaned up)."""

from __future__ import annotations

import uuid

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from typer.testing import CliRunner

from pits.cli import app
from pits.warehouse import airflow_meta as am
from pits.warehouse import cli as db_cli
from pits.warehouse.bootstrap import bootstrap, run_lock
from pits.warehouse.connection import connect
from pits.warehouse.errors import WarehouseError, WarehouseTransientError
from pits.warehouse.settings import Profile

PASSWORD = "pg-test-airflow-meta-pw-" + uuid.uuid4().hex


@pytest.fixture
def names(pg_settings):
    """Unique database/role name (`airflow_meta_t<uuid8>`, covered by the orphan sweep)."""
    value = f"airflow_meta_t{uuid.uuid4().hex[:8]}"
    yield value
    admin = connect(pg_settings, Profile.ADMIN, dbname="postgres", autocommit=True)
    try:
        db, role = sql.Identifier(value), sql.Identifier(value)
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(db))
        admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(role))
    finally:
        admin.close()


@pytest.fixture
def other_role(pg_settings):
    """A different role (same sweepable pattern). Request it BEFORE `names`: it is dropped after
    the database it owns."""
    value = f"airflow_meta_t{uuid.uuid4().hex[:8]}"
    admin = connect(pg_settings, Profile.ADMIN, dbname="postgres", autocommit=True)
    try:
        admin.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(value)))
        yield value
        admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(value)))
    finally:
        admin.close()


def _as_role(settings, role, dbname, password=PASSWORD):
    return psycopg.connect(
        make_conninfo(
            host=settings.host,
            port=settings.port,
            dbname=dbname,
            user=role,
            password=password,
            connect_timeout=10,
            sslmode="disable",
        ),
        autocommit=True,
    )


def _init(settings, names, password=PASSWORD):
    return am.init_airflow_meta(settings, password, dbname=names, role=names)


def test_runs_twice_created_then_unchanged(pg_settings, names):
    first, second = _init(pg_settings, names), _init(pg_settings, names)
    assert (first.status, second.status) == ("created", "unchanged")
    assert (first.database, first.role) == (names, names)


def test_role_attributes_ownership_and_login(pg_settings, names):
    _init(pg_settings, names)
    _init(pg_settings, names)
    with connect(pg_settings, Profile.ADMIN, dbname="postgres", autocommit=True) as admin:
        attrs = admin.execute(
            "SELECT r.rolcanlogin, r.rolsuper, r.rolcreatedb, r.rolcreaterole, r.rolinherit, "
            "r.rolreplication, r.rolbypassrls, a.rolpassword LIKE 'SCRAM-SHA-256$%%' "
            "FROM pg_roles r JOIN pg_authid a ON a.oid = r.oid WHERE r.rolname = %s",
            (names,),
        ).fetchone()
        owner = admin.execute(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s", (names,)
        ).fetchone()
        memberships = admin.execute(
            "SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member "
            "WHERE r.rolname = %s",
            (names,),
        ).fetchone()
    assert attrs == (True, False, False, False, False, False, False, True)
    assert owner == (names,)
    assert memberships == (0,)
    with _as_role(pg_settings, names, names) as conn:  # the owner connects and creates objects
        conn.execute("CREATE TABLE public.t (id int)")
        assert conn.execute("SELECT count(*) FROM public.t").fetchone() == (0,)


def test_role_cannot_connect_to_warehouse(pg_settings, names):
    bootstrap(pg_settings)  # D79: REVOKE ALL ON DATABASE <warehouse> FROM PUBLIC
    _init(pg_settings, names)
    with pytest.raises(psycopg.OperationalError, match="permission denied"):
        _as_role(pg_settings, names, pg_settings.dbname)


def test_pits_roles_cannot_connect_to_airflow_meta(pg_settings, names):
    bootstrap(pg_settings)
    _init(pg_settings, names)
    for profile in (Profile.LOADER, Profile.READER, Profile.TRANSFORMER):
        with pytest.raises(WarehouseError):
            connect(pg_settings, profile, dbname=names)


def test_password_is_reasserted_on_rerun(pg_settings, names):
    _init(pg_settings, names, "old-" + PASSWORD)
    _init(pg_settings, names, PASSWORD)
    with _as_role(pg_settings, names, names) as conn:
        assert conn.execute("SELECT current_user").fetchone() == (names,)
    with pytest.raises(psycopg.OperationalError):
        _as_role(pg_settings, names, names, password="old-" + PASSWORD)


def test_busy_run_lock_is_transient_and_creates_nothing(pg_settings, names):
    with run_lock(pg_settings), pytest.raises(WarehouseTransientError):
        _init(pg_settings, names)
    with connect(pg_settings, Profile.ADMIN, dbname="postgres", autocommit=True) as admin:
        role = admin.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (names,)).fetchone()
        db = admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (names,)).fetchone()
    assert (role, db) == (None, None)


def test_cli_against_real_server(pg_settings, names, monkeypatch):
    """CLI wiring end to end; the unique names and test admin settings are injected."""
    real = am.init_airflow_meta
    monkeypatch.setattr(
        db_cli,
        "init_airflow_meta",
        lambda settings, password: real(pg_settings, password, dbname=names, role=names),
    )
    monkeypatch.setenv(am.PASSWORD_ENV, PASSWORD)
    runner = CliRunner()
    first = runner.invoke(app, ["db", "init-airflow-meta"])
    second = runner.invoke(app, ["db", "init-airflow-meta"])
    assert (first.exit_code, second.exit_code) == (0, 0)
    assert "status=created" in first.output and "status=unchanged" in second.output
    assert PASSWORD not in first.output + second.output


def test_preexisting_database_owned_by_another_role_is_taken_over(pg_settings, other_role, names):
    """Pins the current behavior (review B2): a database with the airflow_meta name that already
    exists under another owner is NOT rejected; the run takes ownership (ALTER DATABASE OWNER TO)
    and revokes PUBLIC. The status only reflects creation, so here it is "created" because the
    role was new; with the role already present it would be "unchanged" although the owner changed.
    """
    with connect(pg_settings, Profile.ADMIN, dbname="postgres", autocommit=True) as admin:
        admin.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(names), sql.Identifier(other_role)
            )
        )
    result = _init(pg_settings, names)
    assert result.status == "created"  # the role did not exist
    with connect(pg_settings, Profile.ADMIN, dbname="postgres", autocommit=True) as admin:
        owner = admin.execute(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s", (names,)
        ).fetchone()
    assert owner == (names,)
    assert _init(pg_settings, names).status == "unchanged"


def test_preexisting_role_and_database_of_another_owner_reports_unchanged(
    pg_settings, other_role, names
):
    """Same takeover, but the role already exists: the status stays "unchanged" although the
    owner changed (the status only reflects creation; review B2)."""
    with connect(pg_settings, Profile.ADMIN, dbname="postgres", autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(names)))
        admin.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(names), sql.Identifier(other_role)
            )
        )
    assert _init(pg_settings, names).status == "unchanged"
    with connect(pg_settings, Profile.ADMIN, dbname="postgres", autocommit=True) as admin:
        owner = admin.execute(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s", (names,)
        ).fetchone()
    assert owner == (names,)

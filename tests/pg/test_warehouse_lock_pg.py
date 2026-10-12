"""D90: one write lock for the warehouse (load, transform, migrate) against a real Postgres 17.

A holder session simulates the writer in progress. Where practical the real code path holds
the lock (a real `open_session`, a real `bootstrap_locked`), so the test proves that the
session/transaction locks with the same key exclude each other on this server version.
"""

from __future__ import annotations

import fx_load_support as fx
import psycopg
import pytest
from fx_load_support import load
from typer.testing import CliRunner

from pits.cli import app
from pits.transform import cli as tcli
from pits.transform import runner as rn
from pits.warehouse import cli as db_cli
from pits.warehouse.bootstrap import bootstrap_locked, run_lock
from pits.warehouse.connection import connect
from pits.warehouse.errors import WarehouseTransientError
from pits.warehouse.locks import WAREHOUSE_LOCK_KEY
from pits.warehouse.migrate import run_migrate
from pits.warehouse.settings import Profile

runner = CliRunner()

# Fixtures of the load tests, re-exposed here by assignment (pytest finds them by attribute name).
base_artifact = fx.base_artifact
store = fx.store
warehouse = fx.warehouse


@pytest.fixture
def transform_build(pg_settings, monkeypatch):
    """`pits transform build` with the test settings; returns (exit_code, output).

    The repository dbt project is only read by `check_project` (exit 1 without a real
    `dbt_project.yml`); dbt itself is stubbed to fail, so nothing is written under transform/.
    """
    monkeypatch.setattr(tcli, "project_dir_factory", rn.default_project_dir)
    monkeypatch.setattr(
        tcli,
        "dbt_runner",
        lambda argv, env: pytest.fail("dbt must not run while the warehouse lock is busy"),
    )
    monkeypatch.setattr(tcli, "settings_factory", lambda env: pg_settings)

    def run():
        result = runner.invoke(app, ["transform", "build"])
        return result.exit_code, result.output

    return run


@pytest.fixture
def db_migrate(pg_settings, monkeypatch):
    monkeypatch.setattr(db_cli, "load_warehouse_settings", lambda env, profiles: pg_settings)
    return lambda: runner.invoke(app, ["db", "migrate"])


def _session_holder(settings) -> psycopg.Connection:
    holder = connect(settings, Profile.ADMIN, autocommit=True)
    holder.execute("SELECT pg_advisory_lock(%s)", (WAREHOUSE_LOCK_KEY,))
    return holder


def _state(admin):
    """Everything the bootstrap or a migration would change: applied versions and the grants."""
    migrations = admin.execute(
        "SELECT version, name, sha256, applied_at FROM ops.schema_migration ORDER BY 1"
    ).fetchall()
    schemas = admin.execute("SELECT nspname, nspacl::text FROM pg_namespace ORDER BY 1").fetchall()
    tables = admin.execute(
        "SELECT n.nspname, c.relname, c.relacl::text FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname IN ('ops', 'landing', 'staging', 'intermediate', 'marts') ORDER BY 1, 2"
    ).fetchall()
    defaults = admin.execute(
        "SELECT defaclrole, defaclnamespace, defaclacl::text FROM pg_default_acl ORDER BY 1, 2"
    ).fetchall()
    return migrations, schemas, tables, defaults


def test_session_holder_blocks_load_transform_and_migrate(
    warehouse,
    pg_settings,
    transform_build,
    db_migrate,
):
    # Revoke something the bootstrap re-grants: if migrate wrote anything, it would show up.
    warehouse.execute(f'REVOKE USAGE ON SCHEMA marts FROM "{pg_settings.roles.reader}"')
    before = _state(warehouse)
    holder = _session_holder(pg_settings)
    try:
        assert load().exit_code == 3
        code, output = transform_build()
        assert code == 3 and "lock" in output, output
        result = db_migrate()
        assert result.exit_code == 3, result.output
        assert _state(warehouse) == before  # no grant re-asserted, no migration recorded
    finally:
        holder.close()
    assert db_migrate().exit_code == 0  # released with the session; the revoke is healed
    assert _state(warehouse) != before


def test_open_load_transaction_blocks_transform(warehouse, pg_settings, transform_build):
    holder = connect(pg_settings, Profile.ADMIN, autocommit=False)
    try:
        row = holder.execute("SELECT pg_try_advisory_xact_lock(%s)", (WAREHOUSE_LOCK_KEY,))
        assert row.fetchone() == (True,)  # the transaction stays open: the lock is held
        code, output = transform_build()
        assert code == 3 and "lock" in output, output
    finally:
        holder.close()


def test_running_transform_blocks_migrate(warehouse, pg_settings, db_migrate):
    with rn.open_session(pg_settings):  # the real session lock of a transform run
        result = db_migrate()
        assert result.exit_code == 3, result.output
        with pytest.raises(WarehouseTransientError):
            run_migrate(pg_settings)


def test_running_migrate_blocks_transform(warehouse, pg_settings, transform_build):
    with run_lock(pg_settings) as maintenance, bootstrap_locked(maintenance, pg_settings):
        code, output = transform_build()  # the real lock a migrate holds until its last migration
        assert code == 3 and "lock" in output, output


def test_running_migrate_blocks_load(warehouse, pg_settings):
    with run_lock(pg_settings) as maintenance, bootstrap_locked(maintenance, pg_settings):
        assert load().exit_code == 3


def test_first_bootstrap_on_a_cluster_without_the_database(pg_settings):
    admin = connect(pg_settings, Profile.ADMIN, dbname="postgres", autocommit=True)
    try:
        exists = "SELECT 1 FROM pg_database WHERE datname = %s"
        assert admin.execute(exists, (pg_settings.dbname,)).fetchone() is None
        assert run_migrate(pg_settings).applied >= 1  # database created, lock taken after it
        assert admin.execute(exists, (pg_settings.dbname,)).fetchone() is not None
    finally:
        admin.close()

"""Transformer (dbt) role, dbt schemas and reader visibility (D86)."""

import pytest
from psycopg import errors as pgerr

from pits.warehouse.bootstrap import bootstrap
from pits.warehouse.connection import connect
from pits.warehouse.migrate import discover_migrations, run_migrate
from pits.warehouse.settings import Profile


@pytest.fixture
def warehouse(pg_settings):
    run_migrate(pg_settings)  # real packaged migrations (0001..0003)
    conns = {p: connect(pg_settings, p, autocommit=True) for p in Profile}
    yield pg_settings, conns
    for conn in conns.values():
        conn.close()


@pytest.mark.parametrize("schema", ["staging", "marts"])
def test_transformer_can_create_table_and_view_in_dbt_schemas(warehouse, schema):
    _, conns = warehouse
    t = conns[Profile.TRANSFORMER]
    t.execute(f"CREATE TABLE {schema}.t_tbl AS SELECT 1 AS id")
    t.execute(f"CREATE VIEW {schema}.t_view AS SELECT 1 AS id")
    t.execute(f"DROP VIEW {schema}.t_view")
    t.execute(f"DROP TABLE {schema}.t_tbl")


@pytest.mark.parametrize("statement", [
    "CREATE TABLE landing.x (id int)",
    "CREATE VIEW landing.v AS SELECT 1 AS id",
    "CREATE TABLE ops.x (id int)",
    "CREATE VIEW ops.v AS SELECT 1 AS id",
    "CREATE TABLE public.x (id int)",
    "CREATE SCHEMA other",
    "CREATE TEMP TABLE t (id int)",
    "INSERT INTO landing.fx_rate (rate_date) VALUES ('2026-01-01')",
    "UPDATE landing.fx_rate SET rate = 1",
    "DELETE FROM landing.fx_rate",
    "TRUNCATE landing.fx_rate",
    "INSERT INTO ops.load_run (dataset) VALUES ('x')",
    "DELETE FROM ops.load_run",
    "SELECT * FROM ops.schema_migration",
])  # fmt: skip
def test_transformer_is_denied(warehouse, statement):
    _, conns = warehouse
    with pytest.raises(pgerr.InsufficientPrivilege):
        conns[Profile.TRANSFORMER].execute(statement)


def test_transformer_can_select_sources_and_has_no_database_create(warehouse):
    _, conns = warehouse
    t = conns[Profile.TRANSFORMER]
    assert t.execute("SELECT count(*) FROM landing.fx_rate").fetchone() == (0,)
    assert t.execute("SELECT count(*) FROM ops.load_run").fetchone() == (0,)
    assert t.execute(
        "SELECT has_database_privilege(current_database(), 'CREATE'), "
        "has_database_privilege(current_database(), 'TEMPORARY'), "
        "has_database_privilege(current_database(), 'CONNECT')"
    ).fetchone() == (False, False, True)


def test_dbt_schemas_are_owned_by_owner_and_closed_to_public(warehouse):
    settings, conns = warehouse
    admin = conns[Profile.ADMIN]
    for schema in ("staging", "intermediate", "marts"):
        row = admin.execute(
            "SELECT pg_get_userbyid(nspowner), has_schema_privilege('public', %s, 'USAGE') "
            "FROM pg_namespace WHERE nspname = %s",
            (schema, schema),
        ).fetchone()
        assert row == (settings.roles.owner, False)


def test_reader_sees_marts_only(warehouse):
    _, conns = warehouse
    reader = conns[Profile.READER]
    row = reader.execute(
        "SELECT has_schema_privilege('marts', 'USAGE'), has_schema_privilege('staging', 'USAGE'), "
        "has_schema_privilege('intermediate', 'USAGE'), has_schema_privilege('marts', 'CREATE')"
    ).fetchone()
    assert row == (True, False, False, False)


def test_reader_reads_transformer_table_in_marts_not_in_staging(warehouse):
    _, conns = warehouse
    t, reader = conns[Profile.TRANSFORMER], conns[Profile.READER]
    t.execute("CREATE TABLE marts.m AS SELECT 1 AS id")
    t.execute("CREATE TABLE staging.s AS SELECT 1 AS id")
    assert reader.execute("SELECT count(*) FROM marts.m").fetchone() == (1,)
    with pytest.raises(pgerr.InsufficientPrivilege):
        reader.execute("SELECT count(*) FROM staging.s")


def test_loader_has_no_access_to_dbt_schemas(warehouse):
    _, conns = warehouse
    with pytest.raises(pgerr.InsufficientPrivilege):
        conns[Profile.LOADER].execute("CREATE TABLE staging.x (id int)")


def test_new_landing_tables_default_to_transformer_select(warehouse):
    settings, conns = warehouse
    admin = conns[Profile.ADMIN]
    admin.execute(f'SET ROLE "{settings.roles.owner}"')
    admin.execute("CREATE TABLE landing.later (id int)")
    admin.execute("RESET ROLE")
    assert conns[Profile.TRANSFORMER].execute("SELECT count(*) FROM landing.later").fetchone() == (
        0,
    )


def test_database_already_at_0002_receives_only_0003(pg_settings, tmp_path):
    packaged = discover_migrations()
    assert len(packaged) == 3
    for m in packaged[:2]:
        (tmp_path / m.filename).write_bytes(m.sql.encode())
    first = run_migrate(pg_settings, tmp_path)  # a database as the real one: only 0001 + 0002
    assert (first.applied, first.skipped) == (2, 0)
    second = run_migrate(pg_settings)  # packaged set
    assert (second.applied, second.skipped) == (1, 2)
    conn = connect(pg_settings, Profile.TRANSFORMER, autocommit=True)
    try:
        assert conn.execute("SELECT count(*) FROM landing.fx_rate").fetchone() == (0,)
    finally:
        conn.close()
    assert run_migrate(pg_settings).skipped == 3


def test_bootstrap_is_idempotent_with_five_schemas(pg_settings):
    bootstrap(pg_settings)
    bootstrap(pg_settings)
    admin = connect(pg_settings, Profile.ADMIN, autocommit=True)
    try:
        count = admin.execute(
            "SELECT count(*) FROM pg_namespace "
            "WHERE nspname IN ('ops', 'landing', 'staging', 'intermediate', 'marts')"
        ).fetchone()
    finally:
        admin.close()
    assert count == (5,)

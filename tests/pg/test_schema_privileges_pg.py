"""Schema constraints and privilege matrix of the real packaged migrations (D79, D81)."""

import json
import uuid

import pytest
from psycopg import errors as pgerr

from pits.warehouse.connection import connect
from pits.warehouse.migrate import discover_migrations, run_migrate
from pits.warehouse.settings import Profile

HASH = "a" * 64

LOAD_RUN_COLUMNS = (
    "dataset, source_system, input_fingerprint, transform_name, rules_version, manifest_key, "
    "manifest_sha256, csv_key, csv_sha256, csv_size_bytes, row_count, coverage_from, "
    "coverage_to, last_input_batch_id, last_input_extraction_date, last_input_finished_at, "
    "normalized_manifest, loader_version"
)


def _load_run_values(**overrides):
    values = {
        "dataset": "fx_rate",
        "source_system": "superfinanciera_trm",
        "input_fingerprint": HASH,
        "transform_name": "trm_to_fx_rate",
        "rules_version": "1",
        "manifest_key": "fx_rate/m.json",
        "manifest_sha256": HASH,
        "csv_key": "fx_rate/fx_rate.csv",
        "csv_sha256": HASH,
        "csv_size_bytes": 100,
        "row_count": 2,
        "coverage_from": "1991-12-02",
        "coverage_to": "1991-12-03",
        "last_input_batch_id": str(uuid.uuid4()),
        "last_input_extraction_date": "2026-10-01",
        "last_input_finished_at": "2026-10-01T12:00:00+00:00",
        "normalized_manifest": json.dumps({"inputs": []}),
        "loader_version": "0.1.0",
    }
    values.update(overrides)
    return values


def _insert_load_run(conn, **overrides):
    values = _load_run_values(**overrides)
    placeholders = ", ".join(f"%({name})s" for name in values)
    row = conn.execute(
        f"INSERT INTO ops.load_run ({', '.join(values)}) VALUES ({placeholders}) RETURNING load_id",
        values,
    ).fetchone()
    return row[0]


_FX_INSERT = (
    "INSERT INTO landing.fx_rate (rate_date, currency_from, currency_to, rate, "
    "source_system, source_reference, load_id) VALUES (%s, %s, %s, %s, %s, %s, %s)"
)


def _insert_fx(conn, load_id, *, day="2026-01-02", cf="USD", ct="COP", rate="4000.5"):
    conn.execute(_FX_INSERT, (day, cf, ct, rate, "superfinanciera_trm", "raw/ref", load_id))


@pytest.fixture
def warehouse(pg_settings):
    run_migrate(pg_settings)  # real packaged migrations
    loader = connect(pg_settings, Profile.LOADER, autocommit=True)
    reader = connect(pg_settings, Profile.READER, autocommit=True)
    admin = connect(pg_settings, Profile.ADMIN, autocommit=True)
    yield pg_settings, loader, reader, admin
    for conn in (loader, reader, admin):
        conn.close()


def test_packaged_migrations_are_the_expected_ones():
    names = [m.filename for m in discover_migrations()]
    assert names == [
        "0001_ops_load_run.sql",
        "0002_landing_fx_rate.sql",
        "0003_transformer_grants.sql",
        "0004_landing_vehicle_fleet_snapshot.sql",
        "0005_landing_divipola_municipality.sql",
        "0006_landing_regional_fleet_brand_count.sql",
    ]


def test_load_run_columns_match_d81(warehouse):
    *_, admin = warehouse
    cols = [
        r[0]
        for r in admin.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'ops' AND table_name = 'load_run' ORDER BY ordinal_position"
        )
    ]
    assert cols == [
        "load_id", "dataset", "source_system", "input_fingerprint", "transform_name",
        "rules_version", "manifest_key", "manifest_sha256", "csv_key", "csv_sha256",
        "csv_size_bytes", "row_count", "coverage_from", "coverage_to", "last_input_batch_id",
        "last_input_extraction_date", "last_input_finished_at", "rows_inserted", "rows_updated",
        "rows_deleted", "normalized_manifest", "loader_version", "loaded_at",
    ]  # fmt: skip


def test_fx_rate_columns_match_csv_header_plus_lineage(warehouse):
    *_, admin = warehouse
    cols = [
        r[0]
        for r in admin.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'landing' AND table_name = 'fx_rate' ORDER BY ordinal_position"
        )
    ]
    assert cols == [
        "rate_date", "currency_from", "currency_to", "rate", "source_system",
        "source_reference", "load_id",
    ]  # fmt: skip


def test_valid_rows_are_accepted(warehouse):
    _, loader, *_ = warehouse
    load_id = _insert_load_run(loader)
    _insert_fx(loader, load_id, rate="0.0000001")
    _insert_fx(loader, load_id, day="2026-01-03", rate="4123.456789")
    assert loader.execute("SELECT count(*) FROM landing.fx_rate").fetchone() == (2,)


@pytest.mark.parametrize("rate", ["0", "-1", "-0.01", "NaN", "Infinity", "-Infinity"])
def test_fx_rate_rejects_bad_rates(warehouse, rate):
    _, loader, *_ = warehouse
    load_id = _insert_load_run(loader)
    with pytest.raises(pgerr.CheckViolation):
        _insert_fx(loader, load_id, rate=rate)


@pytest.mark.parametrize(
    ("cf", "ct"), [("usd", "COP"), ("USD", "cop"), ("US", "COP"), ("USDX", "COP"), ("USD", "USD")]
)
def test_fx_rate_rejects_bad_currencies(warehouse, cf, ct):
    _, loader, *_ = warehouse
    load_id = _insert_load_run(loader)
    with pytest.raises(pgerr.CheckViolation):
        _insert_fx(loader, load_id, cf=cf, ct=ct)


def test_fx_rate_rejects_duplicate_pk_and_unknown_load_id(warehouse):
    _, loader, *_ = warehouse
    load_id = _insert_load_run(loader)
    _insert_fx(loader, load_id)
    with pytest.raises(pgerr.UniqueViolation):
        _insert_fx(loader, load_id)
    with pytest.raises(pgerr.ForeignKeyViolation):
        _insert_fx(loader, load_id + 999, day="2026-02-01")


def test_fx_rate_rejects_bad_source_fields(warehouse):
    _, loader, *_ = warehouse
    load_id = _insert_load_run(loader)
    with pytest.raises(pgerr.CheckViolation):
        loader.execute(_FX_INSERT, ("2026-01-02", "USD", "COP", "1", "Bad-System", "ref", load_id))
    with pytest.raises(pgerr.CheckViolation):
        loader.execute(_FX_INSERT, ("2026-01-02", "USD", "COP", "1", "ok_system", "  ", load_id))


@pytest.mark.parametrize(
    "override",
    [
        {"input_fingerprint": "A" * 64},
        {"manifest_sha256": "a" * 63},
        {"csv_sha256": "g" * 64},
        {"csv_size_bytes": 0},
        {"row_count": 0},
        {"coverage_from": "2026-01-02", "coverage_to": "2026-01-01"},
        {"dataset": "Fx-Rate"},
        {"source_system": "1abc"},
        {"loader_version": " "},
        {"normalized_manifest": json.dumps([1])},
    ],
    ids=lambda o: next(iter(o)),
)
def test_load_run_rejects_bad_values(warehouse, override):
    _, loader, *_ = warehouse
    with pytest.raises(pgerr.CheckViolation):
        _insert_load_run(loader, **override)


def test_load_run_counters_defaults_and_updates(warehouse):
    _, loader, *_ = warehouse
    load_id = _insert_load_run(loader)
    assert loader.execute(
        "SELECT rows_inserted, rows_updated, rows_deleted FROM ops.load_run WHERE load_id = %s",
        (load_id,),
    ).fetchone() == (0, 0, 0)
    loader.execute(
        "UPDATE ops.load_run SET rows_inserted = 5, rows_updated = 1, rows_deleted = 2 "
        "WHERE load_id = %s",
        (load_id,),
    )
    with pytest.raises(pgerr.CheckViolation):
        loader.execute("UPDATE ops.load_run SET rows_deleted = -1 WHERE load_id = %s", (load_id,))


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE landing.x (id int)",
        "CREATE SCHEMA other",
        "TRUNCATE landing.fx_rate",
        "TRUNCATE ops.load_run",
        "DROP TABLE landing.fx_rate",
        "DROP TABLE ops.load_run",
        "ALTER TABLE landing.fx_rate ADD COLUMN x int",
        "SELECT * FROM ops.schema_migration",
        "INSERT INTO ops.schema_migration (version, name, sha256) VALUES (99, 'x', 'a')",
        "DELETE FROM ops.load_run",
        "UPDATE ops.load_run SET row_count = 1",
        "UPDATE ops.load_run SET dataset = 'x'",
        "UPDATE ops.load_run SET loaded_at = now()",
        "CREATE TABLE public.x (id int)",
    ],
)
def test_loader_is_denied(warehouse, statement):
    _, loader, *_ = warehouse
    with pytest.raises(pgerr.InsufficientPrivilege):
        loader.execute(statement)


def test_loader_can_work_on_fx_rate(warehouse):
    _, loader, *_ = warehouse
    load_id = _insert_load_run(loader)
    _insert_fx(loader, load_id)
    loader.execute("UPDATE landing.fx_rate SET rate = 4001")
    assert loader.execute("SELECT rate FROM landing.fx_rate").fetchone() == (4001,)
    loader.execute("DELETE FROM landing.fx_rate")
    # TEMPORARY on the database: the loader stages the CSV in a temp table.
    loader.execute("CREATE TEMP TABLE fx_rate_incoming (rate_date date)")


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO landing.fx_rate (rate_date) VALUES ('2026-01-01')",
        "UPDATE landing.fx_rate SET rate = 1",
        "DELETE FROM landing.fx_rate",
        "TRUNCATE landing.fx_rate",
        "UPDATE ops.load_run SET rows_inserted = 1",
        "DELETE FROM ops.load_run",
        "SELECT * FROM ops.schema_migration",
        "CREATE TABLE landing.x (id int)",
        "CREATE TEMP TABLE t (id int)",
    ],
)
def test_reader_is_denied(warehouse, statement):
    _, _, reader, _ = warehouse
    with pytest.raises(pgerr.InsufficientPrivilege):
        reader.execute(statement)


def test_reader_can_select(warehouse):
    _, loader, reader, _ = warehouse
    load_id = _insert_load_run(loader)
    _insert_fx(loader, load_id)
    assert reader.execute("SELECT count(*) FROM landing.fx_rate").fetchone() == (1,)
    assert reader.execute("SELECT count(*) FROM ops.load_run").fetchone() == (1,)


def test_public_has_no_access(warehouse):
    *_, admin = warehouse
    row = admin.execute(
        "SELECT has_database_privilege('public', current_database(), 'CONNECT'), "
        "has_database_privilege('public', current_database(), 'TEMPORARY'), "
        "has_schema_privilege('public', 'ops', 'USAGE'), "
        "has_schema_privilege('public', 'landing', 'USAGE'), "
        "has_table_privilege('public', 'landing.fx_rate', 'SELECT'), "
        "has_table_privilege('public', 'ops.load_run', 'SELECT'), "
        "has_table_privilege('public', 'ops.schema_migration', 'SELECT')"
    ).fetchone()
    assert row == (False,) * 7


def test_only_owner_owns_the_objects(warehouse):
    settings, *_, admin = warehouse
    owners = admin.execute(
        "SELECT DISTINCT pg_get_userbyid(relowner) FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname IN ('ops', 'landing')"
    ).fetchall()
    assert owners == [(settings.roles.owner,)]

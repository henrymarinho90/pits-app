"""`pits load divipola` against a real Postgres 17: real migrations, real normalizer artifacts.

Each test gets its own database and roles (see conftest). The S3 side is a MemoryRawStore with
one realistic artifact (accents, a comma in names, decimal-comma coordinates, three types).
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from divipola_artifact_support import (
    RAW_BUCKET,
    add_newer_batch,
    build_raw_and_normalized,
    drop_artifact,
    realistic_rows,
)
from psycopg import errors as pgerr
from typer.testing import CliRunner

from pits.cli import app
from pits.ingestion.raw_store import MemoryRawStore
from pits.warehouse import load_cli
from pits.warehouse.connection import connect
from pits.warehouse.divipola_load import open_divipola_warehouse
from pits.warehouse.locks import WAREHOUSE_LOCK_KEY
from pits.warehouse.migrate import run_migrate
from pits.warehouse.settings import Profile

runner = CliRunner()
TABLE = "landing.divipola_municipality"
ROWS = 5


@pytest.fixture(scope="module")
def artifacts():
    raw, norm, result = build_raw_and_normalized()
    return dict(raw.objects), dict(norm.objects), result


@pytest.fixture
def raw_store(artifacts):
    memory = MemoryRawStore()
    memory.objects = dict(artifacts[0])
    return memory


@pytest.fixture
def store(artifacts):
    memory = MemoryRawStore()
    memory.objects = dict(artifacts[1])
    return memory


@pytest.fixture
def result(artifacts):
    return artifacts[2]


@pytest.fixture
def warehouse(pg_settings, monkeypatch, store):
    run_migrate(pg_settings)  # real packaged migrations
    for key, value in {
        "S3_ENDPOINT_URL": "http://127.0.0.1:1",
        "PITS_S3_READER_ACCESS_KEY_ID": "READERKEYEXAMPLE0001",
        "PITS_S3_READER_SECRET_ACCESS_KEY": "s3-secret-0123456789-abcdefghijklmnop",
        "S3_RAW_BUCKET": RAW_BUCKET,
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(load_cli, "client_factory", lambda s: object())
    monkeypatch.setattr(load_cli, "store_factory", lambda c, b: store)
    monkeypatch.setattr(load_cli, "settings_factory", lambda env: pg_settings)
    admin = connect(pg_settings, Profile.ADMIN, autocommit=True)
    yield admin
    admin.close()


def load(*args):
    return runner.invoke(app, ["load", "divipola", *args])


def fields(output: str) -> dict[str, str]:
    (line,) = [x for x in output.splitlines() if x.startswith("outcome=")]
    return dict(part.split("=", 1) for part in line.split())


def count(conn, table=TABLE):
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def snapshot(admin):
    rows = admin.execute(
        "SELECT ctid::text, xmin::text, municipality_code, municipality_name, load_id "
        f"FROM {TABLE} "
        'ORDER BY municipality_code COLLATE "C"'
    ).fetchall()
    runs = admin.execute(
        "SELECT ctid::text, xmin::text, load_id, input_fingerprint, rows_inserted, rows_deleted "
        "FROM ops.load_run ORDER BY load_id"
    ).fetchall()
    return rows, runs


# --- happy path and idempotence -------------------------------------------------------------


def test_first_load_matches_the_artifact(warehouse, result):
    out = load()
    assert out.exit_code == 0, out.output
    f = fields(out.output)
    assert (f["outcome"], f["rows_updated"], f["rows"], f["inserted"], f["updated"]) == (
        "loaded",
        "2025-01-24",
        str(ROWS),
        str(ROWS),
        "0",
    )
    assert f["deleted"] == "0" and f["fingerprint"] == result.fingerprint
    assert f["manifest"] == f"s3://pits-normalized/{result.manifest_key}"
    run = warehouse.execute(
        "SELECT dataset, source_system, coverage_from::text, coverage_to::text, row_count, "
        "rows_inserted, rows_updated, rows_deleted, csv_key, input_fingerprint, transform_name, "
        "normalized_manifest->>'input_fingerprint' FROM ops.load_run"
    ).fetchone()
    assert run == (
        "divipola_municipality",
        "dane_divipola",
        "2025-01-24",
        "2025-01-24",
        ROWS,
        ROWS,
        0,
        0,
        result.manifest_key.replace("manifest.json", "municipality.csv"),
        result.fingerprint,
        "divipola_to_municipality",
        result.fingerprint,
    )
    bogota = warehouse.execute(
        f"SELECT department_name, municipality_name, longitude, latitude, source_system "
        f"FROM {TABLE} WHERE municipality_code = '11001'"
    ).fetchone()
    assert bogota == ("BOGOTÁ, D.C.", "BOGOTÁ, D.C.", "-74,106992", "4,649251", "dane_divipola")
    types = {r[0] for r in warehouse.execute(f"SELECT municipality_type FROM {TABLE}")}
    assert types == {"Municipio", "Isla", "Área no municipalizada"}
    load_ids = {r[0] for r in warehouse.execute(f"SELECT load_id FROM {TABLE}")}
    assert len(load_ids) == 1


def test_second_load_is_already_loaded_and_writes_nothing(warehouse):
    assert load().exit_code == 0
    before = snapshot(warehouse)
    out = load()
    assert out.exit_code == 0, out.output
    f = fields(out.output)
    assert f["outcome"] == "already_loaded" and f["load_id"] == str(before[1][0][2])
    assert (f["inserted"], f["updated"], f["deleted"]) == ("0", "0", "0")
    assert snapshot(warehouse) == before  # same rows, ctid, xmin: nothing was written


def test_newer_artifact_replaces_the_whole_table(warehouse, raw_store, store):
    assert load().exit_code == 0
    newer = add_newer_batch(raw_store, store, realistic_rows()[:2])
    out = load()
    assert out.exit_code == 0, out.output
    f = fields(out.output)
    assert (f["outcome"], f["rows"], f["inserted"], f["deleted"]) == ("loaded", "2", "2", "5")
    assert f["fingerprint"] == newer.fingerprint
    assert count(warehouse) == 2
    assert count(warehouse, "ops.load_run") == 2
    assert fields(load().output)["outcome"] == "already_loaded"


def test_older_artifact_is_exit_1_unless_forced_by_fingerprint(warehouse, raw_store, store, result):
    newer = add_newer_batch(raw_store, store, realistic_rows()[:2])
    assert load().exit_code == 0
    drop_artifact(store, newer.fingerprint)  # the selector now offers only the older artifact
    before = snapshot(warehouse)
    out = load()
    assert out.exit_code == 1 and "older" in out.output
    assert snapshot(warehouse) == before
    forced = load("--fingerprint", result.fingerprint)
    assert forced.exit_code == 0, forced.output
    f = fields(forced.output)
    assert (f["outcome"], f["inserted"], f["deleted"]) == ("loaded", "5", "2")


# --- drift and repair -----------------------------------------------------------------------


def test_manual_delete_is_drift_exit_1_and_repair_fixes_it(warehouse):
    assert load().exit_code == 0
    warehouse.execute(f"DELETE FROM {TABLE} WHERE municipality_code = '05001'")
    out = load()
    assert out.exit_code == 1 and "--repair" in out.output
    repaired = load("--repair")
    assert repaired.exit_code == 0, repaired.output
    f = fields(repaired.output)
    assert (f["outcome"], f["inserted"], f["deleted"]) == ("loaded", "5", "4")
    assert fields(load().output)["outcome"] == "already_loaded"


def test_changed_value_is_detected_by_the_digest(warehouse):
    assert load().exit_code == 0
    # Same count, one text differs: only the rebuilt CSV sees it.
    warehouse.execute(f"UPDATE {TABLE} SET latitude = '6,246632' WHERE municipality_code = '05001'")
    out = load()
    assert out.exit_code == 1 and "sha256" in out.output
    assert fields(load("--repair").output)["deleted"] == "5"


# --- atomicity ------------------------------------------------------------------------------


def test_failure_after_delete_rolls_everything_back(warehouse, raw_store, store, monkeypatch):
    assert load().exit_code == 0
    add_newer_batch(raw_store, store, realistic_rows()[:2])
    before = snapshot(warehouse)

    def boom(conn):
        # The DELETE is visible inside this transaction: prove it ran before failing.
        assert conn.execute(f"SELECT count(*) FROM {TABLE}").fetchone() == (0,)
        raise RuntimeError("injected failure after DELETE")

    @contextmanager
    def factory(settings):
        with open_divipola_warehouse(settings, after_delete=boom) as wh:
            yield wh

    monkeypatch.setattr(load_cli, "divipola_warehouse_factory", factory)
    out = load()
    assert out.exit_code != 0 and isinstance(out.exception, RuntimeError)
    assert snapshot(warehouse) == before  # rows, ctid, xmin and the load_run audit: unchanged
    monkeypatch.setattr(load_cli, "divipola_warehouse_factory", open_divipola_warehouse)
    assert fields(load().output)["outcome"] == "loaded"


def test_first_load_failing_after_delete_leaves_no_trace(warehouse, monkeypatch):
    @contextmanager
    def factory(settings):
        with open_divipola_warehouse(settings, after_delete=lambda c: 1 / 0) as wh:
            yield wh

    monkeypatch.setattr(load_cli, "divipola_warehouse_factory", factory)
    out = load()
    assert out.exit_code != 0 and isinstance(out.exception, ZeroDivisionError)
    assert count(warehouse) == 0 and count(warehouse, "ops.load_run") == 0


def test_terminated_backend_is_exit_3_and_retry_loads(warehouse, monkeypatch):
    def kill_own_backend(conn):
        warehouse.execute("SELECT pg_terminate_backend(%s)", (conn.pgconn.backend_pid,))

    @contextmanager
    def factory(settings):
        with open_divipola_warehouse(settings, after_delete=kill_own_backend) as wh:
            yield wh

    monkeypatch.setattr(load_cli, "divipola_warehouse_factory", factory)
    out = load()
    assert out.exit_code == 3, out.output
    assert count(warehouse) == 0 and count(warehouse, "ops.load_run") == 0
    monkeypatch.setattr(load_cli, "divipola_warehouse_factory", open_divipola_warehouse)
    assert load().exit_code == 0


def test_busy_warehouse_lock_is_exit_3(warehouse, pg_settings):
    holder = connect(pg_settings, Profile.ADMIN, autocommit=True)
    holder.execute("SELECT pg_advisory_lock(%s)", (WAREHOUSE_LOCK_KEY,))
    try:
        out = load()
    finally:
        holder.close()
    assert out.exit_code == 3 and "lock" in out.output
    assert count(warehouse, "ops.load_run") == 0 and count(warehouse) == 0
    assert load().exit_code == 0


def test_corrupt_csv_is_exit_1_and_writes_nothing(warehouse, store):
    key = next(k for k in store.objects if k.endswith("municipality.csv"))
    store.objects[key] = store.objects[key] + b"x"
    out = load()
    assert out.exit_code == 1 and "size" in out.output
    assert count(warehouse) == 0 and count(warehouse, "ops.load_run") == 0


# --- privileges (D124) ----------------------------------------------------------------------


@pytest.fixture
def conns(warehouse, pg_settings):
    assert load().exit_code == 0
    opened = {p: connect(pg_settings, p, autocommit=True) for p in Profile}
    yield opened
    for conn in opened.values():
        conn.close()


def test_loader_can_select_insert_delete_but_not_update_or_truncate(conns):
    loader = conns[Profile.LOADER]
    assert count(loader) == ROWS
    for statement in (
        f"UPDATE {TABLE} SET latitude = '1,0'",
        f"TRUNCATE {TABLE}",
        f"ALTER TABLE {TABLE} ADD COLUMN x int",
        f"DROP TABLE {TABLE}",
    ):
        with pytest.raises(pgerr.InsufficientPrivilege):
            loader.execute(statement)
    assert loader.execute(f"DELETE FROM {TABLE} WHERE municipality_code = '05001'").rowcount == 1


@pytest.mark.parametrize("profile", [Profile.READER, Profile.TRANSFORMER])
def test_reader_and_transformer_only_select(conns, profile):
    conn = conns[profile]
    assert count(conn) == ROWS
    for statement in (
        f"DELETE FROM {TABLE}",
        f"INSERT INTO {TABLE} SELECT * FROM {TABLE} LIMIT 1",
        f"UPDATE {TABLE} SET latitude = '1,0'",
        f"TRUNCATE {TABLE}",
    ):
        with pytest.raises(pgerr.InsufficientPrivilege):
            conn.execute(statement)


# --- table constraints (D124) ---------------------------------------------------------------

_GOOD = {
    "department_code": "05",
    "department_name": "ANTIOQUIA",
    "municipality_code": "05999",
    "municipality_name": "NUEVO",
    "municipality_type": "Municipio",
    "longitude": "-75,5",
    "latitude": "6,2",
    "source_system": "dane_divipola",
    "source_reference": "raw/p0#row=0",
}


def _insert(conn, load_id, **overrides):
    values = {**_GOOD, **overrides, "load_id": load_id}
    columns = ", ".join(values)
    placeholders = ", ".join(f"%({name})s" for name in values)
    conn.execute(f"INSERT INTO {TABLE} ({columns}) VALUES ({placeholders})", values)


def test_table_columns_and_primary_key(warehouse):
    cols = [
        r[0]
        for r in warehouse.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'landing' AND table_name = 'divipola_municipality' "
            "ORDER BY ordinal_position"
        )
    ]
    assert cols == [
        "department_code", "department_name", "municipality_code", "municipality_name",
        "municipality_type", "longitude", "latitude", "source_system", "source_reference",
        "load_id",
    ]  # fmt: skip
    pk = warehouse.execute(
        "SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid "
        "AND a.attnum = ANY (i.indkey) WHERE i.indrelid = %s::regclass AND i.indisprimary",
        (TABLE,),
    ).fetchall()
    assert [r[0] for r in pk] == ["municipality_code"]


@pytest.fixture
def conns_loaded(warehouse, pg_settings):
    assert load().exit_code == 0
    loader = connect(pg_settings, Profile.LOADER, autocommit=True)
    load_id = loader.execute("SELECT max(load_id) FROM ops.load_run").fetchone()[0]
    yield loader, load_id
    loader.close()


@pytest.mark.parametrize(
    "bad",
    [
        {"department_code": "5", "municipality_code": "05998"},
        {"municipality_code": "5999"},
        {"municipality_code": "05A99"},
        {"municipality_code": "08999"},  # prefix differs from department_code
        {"municipality_type": "Corregimiento"},
        {"longitude": "-75.5"},
        {"latitude": ""},
        {"latitude": "abc"},
        {"municipality_name": "  "},
        {"department_name": " ANTIOQUIA"},
        {"source_system": "Bad System"},
        {"source_reference": "  "},
    ],
)
def test_table_rejects_bad_rows(warehouse, conns_loaded, bad):
    loader, load_id = conns_loaded
    _insert(loader, load_id)  # the base row is valid
    loader.execute(f"DELETE FROM {TABLE} WHERE municipality_code = '05999'")
    with pytest.raises(pgerr.CheckViolation):
        _insert(loader, load_id, **bad)


def test_table_rejects_duplicates_and_unknown_load_id(warehouse, conns_loaded):
    loader, load_id = conns_loaded
    _insert(loader, load_id)
    with pytest.raises(pgerr.UniqueViolation):
        _insert(loader, load_id)  # same code
    with pytest.raises(pgerr.UniqueViolation):
        _insert(loader, load_id, municipality_code="05998")  # same name in the department
    with pytest.raises(pgerr.ForeignKeyViolation):
        _insert(loader, load_id + 10_000, municipality_name="OTRO", municipality_code="05997")

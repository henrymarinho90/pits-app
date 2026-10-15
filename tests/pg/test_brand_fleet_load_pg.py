"""`pits load brand-fleet` against a real Postgres 17: real migrations, real normalizer artifacts.

Each test gets its own database and roles (see conftest). The S3 side is a MemoryRawStore holding
one synthetic artifact per source (Boyaca with service/status, Risaralda without them).
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from brand_fleet_artifact_support import (
    RAW_BUCKET,
    add_newer_batch,
    boyaca_rows,
    build_raw_and_normalized,
    drop_artifact,
)
from brand_fleet_support import BOYACA, RISARALDA
from psycopg import errors as pgerr
from typer.testing import CliRunner

from pits.cli import app
from pits.ingestion.raw_store import MemoryRawStore
from pits.warehouse import load_cli
from pits.warehouse.brand_fleet_load import open_brand_fleet_warehouse
from pits.warehouse.connection import connect
from pits.warehouse.locks import WAREHOUSE_LOCK_KEY
from pits.warehouse.migrate import run_migrate
from pits.warehouse.settings import Profile

runner = CliRunner()
TABLE = "landing.regional_fleet_brand_count"
BOYACA_ROWS, BOYACA_VEHICLES = 4, 6
RISARALDA_ROWS, RISARALDA_VEHICLES = 3, 5


@pytest.fixture(scope="module")
def artifacts():
    raw, norm, results = build_raw_and_normalized()
    return dict(raw.objects), dict(norm.objects), results


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
def results(artifacts):
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


def load(source, *args):
    return runner.invoke(app, ["load", "brand-fleet", "--source", source, *args])


def fields(output: str) -> dict[str, str]:
    (line,) = [x for x in output.splitlines() if x.startswith("outcome=")]
    return dict(part.split("=", 1) for part in line.split())


def count(conn, source_system=None, table=TABLE):
    if source_system is None:
        return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    return conn.execute(
        f"SELECT count(*) FROM {table} WHERE source_system = %s", (source_system,)
    ).fetchone()[0]


def snapshot(admin):
    rows = admin.execute(
        "SELECT ctid::text, xmin::text, source_system, vehicle_class, brand, line, service_name, "
        f"vehicle_status, vehicle_count, load_id FROM {TABLE} ORDER BY 3, 4, 5, 6, 7, 8"
    ).fetchall()
    runs = admin.execute(
        "SELECT ctid::text, xmin::text, load_id, source_system, input_fingerprint, rows_inserted, "
        "rows_deleted FROM ops.load_run ORDER BY load_id"
    ).fetchall()
    return rows, runs


# --- happy path and idempotence -------------------------------------------------------------


def test_first_load_matches_the_artifact(warehouse, results):
    out = load("boyaca")
    assert out.exit_code == 0, out.output
    f = fields(out.output)
    assert (f["outcome"], f["source"], f["rows_updated"]) == ("loaded", "boyaca", "2026-07-06")
    assert (f["rows"], f["vehicles"], f["inserted"], f["deleted"]) == (
        str(BOYACA_ROWS),
        str(BOYACA_VEHICLES),
        str(BOYACA_ROWS),
        "0",
    )
    result = results["boyaca"]
    assert f["fingerprint"] == result.fingerprint
    assert f["manifest"] == f"s3://pits-normalized/{result.manifest_key}"
    run = warehouse.execute(
        "SELECT dataset, source_system, coverage_from::text, coverage_to::text, row_count, "
        "rows_inserted, rows_updated, rows_deleted, csv_key, input_fingerprint, transform_name, "
        "normalized_manifest->>'input_fingerprint' FROM ops.load_run"
    ).fetchone()
    assert run == (
        "regional_fleet_brand_count",
        BOYACA.source_system,
        "2026-07-06",
        "2026-07-06",
        BOYACA_ROWS,
        BOYACA_ROWS,
        0,
        0,
        result.manifest_key.replace("manifest.json", "brand_count.csv"),
        result.fingerprint,
        "brand_fleet_to_brand_count",
        result.fingerprint,
    )
    assert warehouse.execute(
        f"SELECT sum(vehicle_count), count(DISTINCT load_id), count(DISTINCT rows_updated::text) "
        f"FROM {TABLE}"
    ).fetchone() == (BOYACA_VEHICLES, 1, 1)
    moto = warehouse.execute(
        f"SELECT brand, service_name, vehicle_status, vehicle_count FROM {TABLE} "
        "WHERE vehicle_class = 'MOTOCICLETA'"
    ).fetchone()
    assert moto == ("MARCA, Y", "PARTICULAR", "CANCELADO", 2)


def test_risaralda_has_null_service_and_status(warehouse):
    assert load("risaralda").exit_code == 0
    rows = warehouse.execute(
        f"SELECT service_name, vehicle_status, vehicle_count FROM {TABLE} ORDER BY vehicle_count"
    ).fetchall()
    assert rows == [(None, None, 1), (None, None, 1), (None, None, 3)]
    assert count(warehouse) == RISARALDA_ROWS


def test_second_load_is_already_loaded_and_writes_nothing(warehouse):
    assert load("boyaca").exit_code == 0
    assert load("risaralda").exit_code == 0
    before = snapshot(warehouse)
    for source, vehicles in (("boyaca", BOYACA_VEHICLES), ("risaralda", RISARALDA_VEHICLES)):
        out = load(source)
        assert out.exit_code == 0, out.output
        f = fields(out.output)
        assert f["outcome"] == "already_loaded" and f["vehicles"] == str(vehicles)
        assert (f["inserted"], f["deleted"]) == ("0", "0")
    assert snapshot(warehouse) == before  # same rows, ctid, xmin: nothing was written


def test_one_source_never_deletes_the_other(warehouse, raw_store, store):
    assert load("boyaca").exit_code == 0
    assert load("risaralda").exit_code == 0
    risaralda_before = warehouse.execute(
        f"SELECT ctid::text, xmin::text, vehicle_class, brand, line, vehicle_count FROM {TABLE} "
        "WHERE source_system = %s ORDER BY 3, 4, 5",
        (RISARALDA.source_system,),
    ).fetchall()
    newer = add_newer_batch(raw_store, store, BOYACA, boyaca_rows()[:2])
    out = load("boyaca")
    assert out.exit_code == 0, out.output
    f = fields(out.output)
    assert (f["outcome"], f["rows"], f["inserted"], f["deleted"]) == (
        "loaded",
        "1",
        "1",
        str(BOYACA_ROWS),
    )
    assert f["fingerprint"] == newer.fingerprint
    assert count(warehouse, BOYACA.source_system) == 1
    assert count(warehouse, RISARALDA.source_system) == RISARALDA_ROWS
    risaralda_after = warehouse.execute(
        f"SELECT ctid::text, xmin::text, vehicle_class, brand, line, vehicle_count FROM {TABLE} "
        "WHERE source_system = %s ORDER BY 3, 4, 5",
        (RISARALDA.source_system,),
    ).fetchall()
    assert risaralda_after == risaralda_before
    assert count(warehouse, table="ops.load_run") == 3
    assert fields(load("boyaca").output)["outcome"] == "already_loaded"
    assert fields(load("risaralda").output)["outcome"] == "already_loaded"


def test_older_artifact_is_exit_1_unless_forced_by_fingerprint(
    warehouse, raw_store, store, results
):
    newer = add_newer_batch(raw_store, store, BOYACA, boyaca_rows()[:2])
    assert load("boyaca").exit_code == 0
    drop_artifact(store, newer.fingerprint)  # the selector now offers only the older artifact
    before = snapshot(warehouse)
    out = load("boyaca")
    assert out.exit_code == 1 and "older" in out.output
    assert snapshot(warehouse) == before
    forced = load("boyaca", "--fingerprint", results["boyaca"].fingerprint)
    assert forced.exit_code == 0, forced.output
    f = fields(forced.output)
    assert (f["outcome"], f["inserted"], f["deleted"]) == ("loaded", str(BOYACA_ROWS), "1")


def test_regression_is_judged_per_source(warehouse, raw_store, store):
    add_newer_batch(raw_store, store, BOYACA, boyaca_rows()[:2])
    assert load("boyaca").exit_code == 0
    # Risaralda has no loaded run yet, so its older-looking input is a plain first load.
    assert load("risaralda").exit_code == 0


# --- drift and repair -----------------------------------------------------------------------


def test_manual_delete_is_drift_exit_1_and_repair_fixes_it(warehouse):
    assert load("boyaca").exit_code == 0
    assert load("risaralda").exit_code == 0
    warehouse.execute(f"DELETE FROM {TABLE} WHERE brand = 'MARCA Z'")
    out = load("boyaca")
    assert out.exit_code == 1 and "--repair" in out.output
    repaired = load("boyaca", "--repair")
    assert repaired.exit_code == 0, repaired.output
    f = fields(repaired.output)
    assert (f["outcome"], f["inserted"], f["deleted"]) == (
        "loaded",
        str(BOYACA_ROWS),
        str(BOYACA_ROWS - 1),
    )
    assert fields(load("boyaca").output)["outcome"] == "already_loaded"
    assert count(warehouse, RISARALDA.source_system) == RISARALDA_ROWS


def test_changed_text_is_detected_by_the_digest(warehouse):
    assert load("boyaca").exit_code == 0
    # Same count and total, one text differs: only the rebuilt CSV sees it.
    warehouse.execute(f"UPDATE {TABLE} SET line = 'L9' WHERE line = 'L3'")
    out = load("boyaca")
    assert out.exit_code == 1 and "sha256" in out.output
    assert fields(load("boyaca", "--repair").output)["deleted"] == str(BOYACA_ROWS)


def test_changed_count_with_same_row_count_is_detected(warehouse):
    assert load("boyaca").exit_code == 0
    warehouse.execute(f"UPDATE {TABLE} SET vehicle_count = vehicle_count + 1 WHERE line = 'L3'")
    out = load("boyaca")
    assert out.exit_code == 1 and "vehicle total" in out.output


def test_changed_rows_updated_is_detected(warehouse):
    assert load("boyaca").exit_code == 0
    warehouse.execute(f"UPDATE {TABLE} SET rows_updated = '2020-01-01' WHERE line = 'L3'")
    out = load("boyaca")
    assert out.exit_code == 1 and "rows_updated" in out.output


# --- atomicity ------------------------------------------------------------------------------


def test_failure_after_delete_rolls_everything_back(warehouse, raw_store, store, monkeypatch):
    assert load("boyaca").exit_code == 0
    assert load("risaralda").exit_code == 0
    add_newer_batch(raw_store, store, BOYACA, boyaca_rows()[:2])
    before = snapshot(warehouse)

    def boom(conn):
        # The DELETE is visible inside this transaction: prove it ran before failing.
        assert conn.execute(
            f"SELECT count(*) FROM {TABLE} WHERE source_system = %s", (BOYACA.source_system,)
        ).fetchone() == (0,)
        raise RuntimeError("injected failure after DELETE")

    @contextmanager
    def factory(settings):
        with open_brand_fleet_warehouse(settings, after_delete=boom) as wh:
            yield wh

    monkeypatch.setattr(load_cli, "brand_fleet_warehouse_factory", factory)
    out = load("boyaca")
    assert out.exit_code != 0 and isinstance(out.exception, RuntimeError)
    assert snapshot(warehouse) == before  # rows, ctid, xmin and the load_run audit: unchanged
    monkeypatch.setattr(load_cli, "brand_fleet_warehouse_factory", open_brand_fleet_warehouse)
    assert fields(load("boyaca").output)["outcome"] == "loaded"


def test_first_load_failing_after_delete_leaves_no_trace(warehouse, monkeypatch):
    @contextmanager
    def factory(settings):
        with open_brand_fleet_warehouse(settings, after_delete=lambda c: 1 / 0) as wh:
            yield wh

    monkeypatch.setattr(load_cli, "brand_fleet_warehouse_factory", factory)
    out = load("risaralda")
    assert out.exit_code != 0 and isinstance(out.exception, ZeroDivisionError)
    assert count(warehouse) == 0 and count(warehouse, table="ops.load_run") == 0


def test_terminated_backend_is_exit_3_and_retry_loads(warehouse, monkeypatch):
    def kill_own_backend(conn):
        warehouse.execute("SELECT pg_terminate_backend(%s)", (conn.pgconn.backend_pid,))

    @contextmanager
    def factory(settings):
        with open_brand_fleet_warehouse(settings, after_delete=kill_own_backend) as wh:
            yield wh

    monkeypatch.setattr(load_cli, "brand_fleet_warehouse_factory", factory)
    out = load("boyaca")
    assert out.exit_code == 3, out.output
    assert count(warehouse) == 0 and count(warehouse, table="ops.load_run") == 0
    monkeypatch.setattr(load_cli, "brand_fleet_warehouse_factory", open_brand_fleet_warehouse)
    assert load("boyaca").exit_code == 0


def test_busy_warehouse_lock_is_exit_3(warehouse, pg_settings):
    holder = connect(pg_settings, Profile.ADMIN, autocommit=True)
    holder.execute("SELECT pg_advisory_lock(%s)", (WAREHOUSE_LOCK_KEY,))
    try:
        out = load("boyaca")
    finally:
        holder.close()
    assert out.exit_code == 3 and "lock" in out.output
    assert count(warehouse, table="ops.load_run") == 0 and count(warehouse) == 0
    assert load("boyaca").exit_code == 0


def test_corrupt_csv_is_exit_1_and_writes_nothing(warehouse, store):
    key = next(k for k in store.objects if "boyaca" in k and k.endswith("brand_count.csv"))
    store.objects[key] = store.objects[key] + b"x"
    out = load("boyaca")
    assert out.exit_code == 1 and "size" in out.output
    assert count(warehouse) == 0 and count(warehouse, table="ops.load_run") == 0


# --- privileges (D138) ----------------------------------------------------------------------


@pytest.fixture
def conns(warehouse, pg_settings):
    assert load("boyaca").exit_code == 0
    opened = {p: connect(pg_settings, p, autocommit=True) for p in Profile}
    yield opened
    for conn in opened.values():
        conn.close()


def test_loader_can_select_insert_delete_but_not_update_or_truncate(conns):
    loader = conns[Profile.LOADER]
    assert count(loader) == BOYACA_ROWS
    for statement in (
        f"UPDATE {TABLE} SET brand = 'X'",
        f"TRUNCATE {TABLE}",
        f"ALTER TABLE {TABLE} ADD COLUMN x int",
        f"DROP TABLE {TABLE}",
    ):
        with pytest.raises(pgerr.InsufficientPrivilege):
            loader.execute(statement)
    assert loader.execute(f"DELETE FROM {TABLE} WHERE brand = 'MARCA Z'").rowcount == 1


@pytest.mark.parametrize("profile", [Profile.READER, Profile.TRANSFORMER])
def test_reader_and_transformer_only_select(conns, profile):
    conn = conns[profile]
    assert count(conn) == BOYACA_ROWS
    for statement in (
        f"DELETE FROM {TABLE}",
        f"INSERT INTO {TABLE} SELECT * FROM {TABLE} LIMIT 1",
        f"UPDATE {TABLE} SET brand = 'X'",
        f"TRUNCATE {TABLE}",
    ):
        with pytest.raises(pgerr.InsufficientPrivilege):
            conn.execute(statement)


# --- table constraints (D138) ---------------------------------------------------------------

_GOOD = {
    "source_system": "gobernacion_boyaca_parque_automotor",
    "rows_updated": "2026-07-06",
    "vehicle_class": "AUTOMOVIL",
    "brand": "NUEVA",
    "line": "N1",
    "service_name": "PARTICULAR",
    "vehicle_status": "ACTIVO",
    "vehicle_count": 3,
    "source_reference": "raw/manifest.json",
}


def _insert(conn, load_id, **overrides):
    values = {**_GOOD, **overrides, "load_id": load_id}
    columns = ", ".join(values)
    placeholders = ", ".join(f"%({name})s" for name in values)
    conn.execute(f"INSERT INTO {TABLE} ({columns}) VALUES ({placeholders})", values)


def test_table_columns_and_unique_constraint(warehouse):
    cols = [
        r[0]
        for r in warehouse.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'landing' AND table_name = 'regional_fleet_brand_count' "
            "ORDER BY ordinal_position"
        )
    ]
    assert cols == [
        "source_system", "rows_updated", "vehicle_class", "brand", "line", "service_name",
        "vehicle_status", "vehicle_count", "source_reference", "load_id",
    ]  # fmt: skip
    definition = warehouse.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname = 'regional_fleet_brand_count_uq'"
    ).fetchone()[0]
    assert "NULLS NOT DISTINCT" in definition
    nullable = dict(
        warehouse.execute(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'landing' AND table_name = 'regional_fleet_brand_count'"
        ).fetchall()
    )
    assert nullable["service_name"] == "YES" and nullable["vehicle_status"] == "YES"
    assert nullable["brand"] == "NO" and nullable["vehicle_count"] == "NO"


@pytest.fixture
def conns_loaded(warehouse, pg_settings):
    assert load("boyaca").exit_code == 0
    loader = connect(pg_settings, Profile.LOADER, autocommit=True)
    load_id = loader.execute("SELECT max(load_id) FROM ops.load_run").fetchone()[0]
    yield loader, load_id
    loader.close()


@pytest.mark.parametrize(
    "bad",
    [
        {"vehicle_count": 0},
        {"vehicle_count": -1},
        {"vehicle_class": "  "},
        {"brand": ""},
        {"line": " "},
        {"service_name": ""},
        {"vehicle_status": "  "},
        {"source_system": "Bad System"},
        {"source_reference": "  "},
    ],
)
def test_table_rejects_bad_rows(warehouse, conns_loaded, bad):
    loader, load_id = conns_loaded
    with pytest.raises(pgerr.CheckViolation):
        _insert(loader, load_id, **bad)


def test_nulls_not_distinct_rejects_duplicates_with_null_keys(warehouse, conns_loaded):
    loader, load_id = conns_loaded
    null_keys = {"service_name": None, "vehicle_status": None}
    _insert(loader, load_id, **null_keys)
    with pytest.raises(pgerr.UniqueViolation):
        _insert(loader, load_id, **null_keys)  # a plain UNIQUE would let this through
    _insert(loader, load_id, service_name="PARTICULAR", vehicle_status=None)  # not a duplicate
    with pytest.raises(pgerr.UniqueViolation):
        _insert(loader, load_id, service_name="PARTICULAR", vehicle_status=None)
    _insert(loader, load_id, source_system="gobernacion_risaralda_parque_automotor", **null_keys)


def test_table_rejects_exact_duplicates_and_unknown_load_id(warehouse, conns_loaded):
    loader, load_id = conns_loaded
    _insert(loader, load_id)
    with pytest.raises(pgerr.UniqueViolation):
        _insert(loader, load_id)
    with pytest.raises(pgerr.ForeignKeyViolation):
        _insert(loader, load_id + 10_000, brand="OTRA")

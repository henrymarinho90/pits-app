"""`pits load vehicle-fleet` against a real Postgres 17: real migrations, real normalizer artifacts.

Each test gets its own database and roles (see conftest). The S3 side is a MemoryRawStore with
two publications: 2026-09 (25.000 rows, two parts) and 2026-10 (tricky text values, one part).
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Callable
from contextlib import contextmanager

import fleet_load_support as fl
import pytest
from fleet_artifact_support import DAY, RAW_BUCKET, add_newer_batch, drop_artifact, tricky_rows
from fleet_load_support import BIG_ROWS, fields, load
from psycopg import errors as pgerr
from runt_support import B1, put_runt_batch, raw_row

from pits.ingestion.raw_store import MemoryRawStore
from pits.normalized.fleet_csv import HEADER_BYTES, FleetPart, logical_content
from pits.normalized.fleet_manifest import FleetManifest, PartEntry
from pits.sources.runt.normalize import normalize_runt
from pits.warehouse import load_cli
from pits.warehouse.connection import connect
from pits.warehouse.locks import WAREHOUSE_LOCK_KEY
from pits.warehouse.settings import Profile
from pits.warehouse.vehicle_fleet_load import open_fleet_warehouse

# Fixtures re-exposed by assignment (pytest finds them by attribute name).
fleet_artifacts = fl.fleet_artifacts
raw_store = fl.raw_store
store = fl.store
results = fl.results
warehouse = fl.warehouse

TABLE = "landing.vehicle_fleet_snapshot"
TEN_ROWS = 9  # len(TRICKY_NAMES)


def snapshot(admin):
    rows = admin.execute(
        "SELECT ctid::text, xmin::text, publication_month, department_name, municipality_name, "
        f"service_name, vehicle_status, vehicle_class, registration_year, vehicle_count, load_id "
        f'FROM {TABLE} ORDER BY publication_month, municipality_name COLLATE "C", '
        "department_name, registration_year"
    ).fetchall()
    runs = admin.execute(
        "SELECT ctid::text, xmin::text, load_id, input_fingerprint, coverage_from, rows_inserted, "
        "rows_updated, rows_deleted FROM ops.load_run ORDER BY load_id"
    ).fetchall()
    return rows, runs


def publication_rows(admin, month):
    return admin.execute(
        f"SELECT ctid::text, xmin::text, municipality_name FROM {TABLE} "
        'WHERE publication_month = %s ORDER BY municipality_name COLLATE "C"',
        (month,),
    ).fetchall()


def count(admin, table):
    return admin.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def craft(
    store,
    results,
    publication: str,
    edit: Callable[[int, list[str]], list[str]],
) -> None:
    """Rewrite a committed artifact: `edit(part_index, data_lines)` returns the new lines.

    Part hashes, sizes and the logical content hash are recomputed, so the manifest still
    validates: only the warehouse (or its guards) can reject the data.
    """
    original = results[publication]
    manifest = FleetManifest.from_json(store.get(original.manifest_key))
    entries, bodies = [], []
    for index, entry in enumerate(manifest.parts):
        lines = edit(index, store.get(entry.key).decode().splitlines()[1:])
        body = HEADER_BYTES + ("\n".join(lines) + "\n").encode()
        store.objects[entry.key] = body
        bodies.append(body)
        entries.append(
            PartEntry(entry.key, hashlib.sha256(body).hexdigest(), len(body), entry.row_count)
        )
    content_sha, content_size = logical_content(
        [FleetPart(b, e.row_count) for b, e in zip(bodies, entries, strict=True)]
    )
    crafted = dataclasses.replace(
        manifest,
        parts=tuple(entries),
        content_sha256=content_sha,
        content_size_bytes=content_size,
    )
    store.objects[original.manifest_key] = crafted.to_json()


def first_line_edit(change: Callable[[str], str]) -> Callable[[int, list[str]], list[str]]:
    """Edit only the first data line of the first part."""

    def edit(index: int, lines: list[str]) -> list[str]:
        return [change(lines[0]), *lines[1:]] if index == 0 else lines

    return edit


# --- happy path and idempotence -------------------------------------------------------------


def test_first_load_loads_both_publications_in_order(warehouse, results):
    result = load()
    assert result.exit_code == 0, result.output
    nine, ten = fields(result.output)
    assert (nine["outcome"], nine["publication"]) == ("loaded", "2026-09")
    assert (ten["outcome"], ten["publication"]) == ("loaded", "2026-10")
    assert nine["fingerprint"] == results["2026-09"].fingerprint
    assert (nine["rows"], nine["inserted"], nine["updated"], nine["deleted"]) == (
        str(BIG_ROWS),
        str(BIG_ROWS),
        "0",
        "0",
    )
    assert nine["manifest"] == f"s3://pits-normalized/{results['2026-09'].manifest_key}"
    assert int(nine["load_id"]) < int(ten["load_id"])
    assert count(warehouse, TABLE) == BIG_ROWS + TEN_ROWS
    runs = warehouse.execute(
        "SELECT dataset, source_system, coverage_from::text, coverage_to::text, row_count, "
        "rows_inserted, rows_updated, rows_deleted, csv_key, input_fingerprint, "
        "normalized_manifest->>'input_fingerprint', transform_name FROM ops.load_run "
        "ORDER BY load_id"
    ).fetchall()
    assert [r[:4] for r in runs] == [
        ("vehicle_fleet_snapshot", "mintransporte_runt_parque", "2026-09-01", "2026-09-01"),
        ("vehicle_fleet_snapshot", "mintransporte_runt_parque", "2026-10-01", "2026-10-01"),
    ]
    assert runs[0][4:8] == (BIG_ROWS, BIG_ROWS, 0, 0)
    assert runs[1][4:8] == (TEN_ROWS, TEN_ROWS, 0, 0)
    prefix = results["2026-10"].manifest_key.removesuffix("manifest.json")
    assert runs[1][8:] == (prefix, results["2026-10"].fingerprint) + (
        results["2026-10"].fingerprint,
        "runt_to_vehicle_fleet_snapshot",
    )
    totals = warehouse.execute(
        f"SELECT publication_month, count(*), sum(vehicle_count), min(source_system) FROM {TABLE} "
        "GROUP BY 1 ORDER BY 1"
    ).fetchall()
    assert [t[0] for t in totals] == [9, 10] and {t[3] for t in totals} == {
        "mintransporte_runt_parque"
    }


def test_second_load_is_already_loaded_and_writes_nothing(warehouse):
    assert load().exit_code == 0
    before = snapshot(warehouse)
    result = load()
    assert result.exit_code == 0, result.output
    outs = fields(result.output)
    assert [o["outcome"] for o in outs] == ["already_loaded", "already_loaded"]
    assert [o["load_id"] for o in outs] == [str(r[2]) for r in before[1]]
    assert all((o["inserted"], o["updated"], o["deleted"]) == ("0", "0", "0") for o in outs)
    assert snapshot(warehouse) == before  # same rows, ctid, xmin: nothing was written


def test_publication_filter_loads_only_that_publication(warehouse):
    result = load("--publication", "2026-10")
    assert result.exit_code == 0, result.output
    assert [o["publication"] for o in fields(result.output)] == ["2026-10"]
    assert count(warehouse, TABLE) == TEN_ROWS and count(warehouse, "ops.load_run") == 1


def test_table_is_the_artifact_in_every_cell(warehouse, store, results):
    assert load().exit_code == 0
    manifest = FleetManifest.from_json(store.get(results["2026-10"].manifest_key))
    total = warehouse.execute(
        f"SELECT sum(vehicle_count) FROM {TABLE} WHERE publication_month = 10"
    ).fetchone()[0]
    assert total == manifest.vehicle_count_total
    names = {
        r[0]
        for r in warehouse.execute(
            f"SELECT municipality_name FROM {TABLE} WHERE publication_month = 10"
        )
    }
    assert {"ÑANDÚ", "MUNI, X", 'A "Q" B', "bogotá", "BOGOTÁ"} <= names


# --- publications are independent -----------------------------------------------------------


def test_replacing_one_publication_never_touches_the_other(warehouse, raw_store, store, results):
    assert load().exit_code == 0
    nine_before = publication_rows(warehouse, 9)
    ten_before = publication_rows(warehouse, 10)
    new_rows = tricky_rows(year=2026, month=10)[:4]
    newer = add_newer_batch(raw_store, store, (2026, 10), new_rows)
    result = load()
    assert result.exit_code == 0, result.output
    nine, ten = fields(result.output)
    assert nine["outcome"] == "already_loaded"
    assert (ten["outcome"], ten["fingerprint"]) == ("loaded", newer.fingerprint)
    assert (ten["rows"], ten["inserted"], ten["updated"], ten["deleted"]) == ("4", "4", "0", "9")
    assert publication_rows(warehouse, 9) == nine_before  # same ctid and xmin
    assert publication_rows(warehouse, 10) != ten_before
    assert count(warehouse, f"{TABLE} WHERE publication_month = 10") == 4
    last = warehouse.execute(
        "SELECT rows_inserted, rows_updated, rows_deleted FROM ops.load_run ORDER BY load_id DESC"
    ).fetchone()
    assert last == (4, 0, 9)
    assert [o["outcome"] for o in fields(load().output)] == ["already_loaded"] * 2


def test_older_artifact_is_exit_1_unless_forced_by_fingerprint(
    warehouse, raw_store, store, results
):
    newer = add_newer_batch(raw_store, store, (2026, 10), tricky_rows(year=2026, month=10)[:4])
    assert load().exit_code == 0
    drop_artifact(store, newer.fingerprint)  # the selector now offers only the older artifact
    before = snapshot(warehouse)
    result = load("--publication", "2026-10")
    assert result.exit_code == 1 and "older" in result.output
    assert snapshot(warehouse) == before
    forced = load("--fingerprint", results["2026-10"].fingerprint)
    assert forced.exit_code == 0, forced.output
    (out,) = fields(forced.output)
    assert (out["outcome"], out["inserted"], out["deleted"]) == ("loaded", "9", "4")
    assert count(warehouse, f"{TABLE} WHERE publication_month = 10") == TEN_ROWS


# --- drift and repair -----------------------------------------------------------------------


def test_manual_delete_is_drift_exit_1_and_repair_fixes_it(warehouse):
    assert load().exit_code == 0
    warehouse.execute(f"DELETE FROM {TABLE} WHERE municipality_name = 'Z'")
    nine_before = publication_rows(warehouse, 9)
    result = load()
    assert result.exit_code == 1 and "--repair" in result.output and "2026-10" in result.output
    assert [o["publication"] for o in fields(result.output)] == ["2026-09"]  # earlier one done
    repaired = load("--repair")
    assert repaired.exit_code == 0, repaired.output
    nine, ten = fields(repaired.output)
    assert nine["outcome"] == "already_loaded"
    assert (ten["outcome"], ten["rows"], ten["inserted"], ten["updated"], ten["deleted"]) == (
        "loaded",
        "9",
        "9",
        "0",
        "8",
    )
    assert publication_rows(warehouse, 9) == nine_before
    assert [o["outcome"] for o in fields(load().output)] == ["already_loaded"] * 2


def test_changed_value_and_extra_row_are_detected_by_the_digest(warehouse):
    assert load().exit_code == 0
    # Same count and same vehicle total, one text differs: only the rebuilt CSV sees it.
    warehouse.execute(
        f"UPDATE {TABLE} SET vehicle_status = 'INACTIVO' WHERE municipality_name = 'a'"
    )
    result = load()
    assert result.exit_code == 1 and "sha256" in result.output
    assert fields(load("--repair").output)[1]["deleted"] == "9"


# --- atomicity ------------------------------------------------------------------------------


def test_failure_after_delete_rolls_everything_back(warehouse, raw_store, store, monkeypatch):
    assert load().exit_code == 0
    add_newer_batch(raw_store, store, (2026, 10), tricky_rows(year=2026, month=10)[:4])
    before = snapshot(warehouse)

    def boom(conn):
        # The DELETE is visible inside this transaction: prove it ran before failing.
        left = conn.execute(f"SELECT count(*) FROM {TABLE} WHERE publication_month = 10")
        assert left.fetchone() == (0,)
        raise RuntimeError("injected failure after DELETE")

    @contextmanager
    def factory(settings):
        with open_fleet_warehouse(settings, after_delete=boom) as wh:
            yield wh

    monkeypatch.setattr(load_cli, "fleet_warehouse_factory", factory)
    result = load()
    assert result.exit_code != 0 and isinstance(result.exception, RuntimeError)
    assert snapshot(warehouse) == before  # rows, ctid, xmin and the load_run audit: unchanged
    monkeypatch.setattr(load_cli, "fleet_warehouse_factory", open_fleet_warehouse)
    assert fields(load().output)[1]["outcome"] == "loaded"


def test_first_load_failing_after_delete_leaves_no_trace(warehouse, monkeypatch):
    @contextmanager
    def factory(settings):
        with open_fleet_warehouse(settings, after_delete=lambda c: 1 / 0) as wh:
            yield wh

    monkeypatch.setattr(load_cli, "fleet_warehouse_factory", factory)
    result = load()
    assert result.exit_code != 0 and isinstance(result.exception, ZeroDivisionError)
    assert count(warehouse, TABLE) == 0 and count(warehouse, "ops.load_run") == 0


def test_terminated_backend_is_exit_3_and_retry_loads(warehouse, monkeypatch):
    def kill_own_backend(conn):
        warehouse.execute("SELECT pg_terminate_backend(%s)", (conn.pgconn.backend_pid,))

    @contextmanager
    def factory(settings):
        with open_fleet_warehouse(settings, after_delete=kill_own_backend) as wh:
            yield wh

    monkeypatch.setattr(load_cli, "fleet_warehouse_factory", factory)
    result = load()
    assert result.exit_code == 3, result.output
    assert count(warehouse, TABLE) == 0 and count(warehouse, "ops.load_run") == 0
    monkeypatch.setattr(load_cli, "fleet_warehouse_factory", open_fleet_warehouse)
    assert load().exit_code == 0


def test_busy_warehouse_lock_is_exit_3(warehouse, pg_settings):
    holder = connect(pg_settings, Profile.ADMIN, autocommit=True)
    holder.execute("SELECT pg_advisory_lock(%s)", (WAREHOUSE_LOCK_KEY,))
    try:
        result = load()
    finally:
        holder.close()
    assert result.exit_code == 3 and "lock" in result.output
    assert count(warehouse, "ops.load_run") == 0 and count(warehouse, TABLE) == 0
    assert load().exit_code == 0


# --- data the table must reject: exit 1 and nothing written ---------------------------------


def test_nul_byte_in_a_value_is_a_clean_exit_1(warehouse, store):
    """The normalizer accepts NUL inside a text value; PostgreSQL text cannot hold it."""
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_runt_batch(raw, B1, DAY, [raw_row(0, nombre_municipio="MU\x00NI")])
    assert [r.rows for r in normalize_runt(raw, norm, raw_bucket=RAW_BUCKET)] == [1]
    store.objects.clear()
    store.objects.update(norm.objects)
    result = load()
    assert result.exit_code == 1, result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)  # no traceback
    assert "Traceback" not in result.output
    assert count(warehouse, TABLE) == 0 and count(warehouse, "ops.load_run") == 0


def test_rows_of_another_publication_inside_an_artifact_are_rejected(warehouse, store, results):
    assert load("--publication", "2026-09").exit_code == 0
    nine_before = publication_rows(warehouse, 9)
    craft(
        store, results, "2026-10", first_line_edit(lambda ln: ln.replace("2026,10,", "2026,9,", 1))
    )
    result = load()
    assert result.exit_code == 1 and "do not belong" in result.output
    assert publication_rows(warehouse, 9) == nine_before
    assert count(warehouse, TABLE) == BIG_ROWS and count(warehouse, "ops.load_run") == 1


def test_registration_year_after_publication_is_rejected_by_the_table(warehouse, store, results):
    craft(store, results, "2026-10", first_line_edit(lambda ln: ln.replace(",1999,", ",2027,", 1)))
    result = load("--publication", "2026-10")
    assert result.exit_code == 1, result.output
    assert count(warehouse, TABLE) == 0 and count(warehouse, "ops.load_run") == 0


def test_duplicate_primary_key_across_parts_is_exit_1(warehouse, store, results):
    manifest = FleetManifest.from_json(store.get(results["2026-09"].manifest_key))
    assert len(manifest.parts) == 2
    first_row = store.get(manifest.parts[0].key).decode().splitlines()[1]

    def edit(index, lines):  # first row of part 2 becomes a copy of the first row of part 1
        return [first_row, *lines[1:]] if index == 1 else lines

    craft(store, results, "2026-09", edit)
    result = load("--publication", "2026-09")
    assert result.exit_code == 1, result.output
    assert count(warehouse, TABLE) == 0 and count(warehouse, "ops.load_run") == 0


def test_corrupt_part_is_exit_1_before_anything_is_written(warehouse, store, results):
    manifest = FleetManifest.from_json(store.get(results["2026-10"].manifest_key))
    data = bytearray(store.get(manifest.parts[0].key))
    data[-2] ^= 1
    store.objects[manifest.parts[0].key] = bytes(data)
    result = load()
    assert result.exit_code == 1 and "sha256" in result.output
    assert count(warehouse, "ops.load_run") == 1  # 2026-09 committed before 2026-10 failed


# --- privileges (D99) -----------------------------------------------------------------------


@pytest.fixture
def conns(warehouse, pg_settings):
    assert load().exit_code == 0
    opened = {p: connect(pg_settings, p, autocommit=True) for p in Profile}
    yield opened
    for conn in opened.values():
        conn.close()


def test_loader_can_select_insert_delete_but_not_update_or_truncate(conns):
    loader = conns[Profile.LOADER]
    assert count(loader, TABLE) == BIG_ROWS + TEN_ROWS
    for statement in (
        f"UPDATE {TABLE} SET vehicle_count = 1",
        f"UPDATE {TABLE} SET load_id = load_id",
        f"TRUNCATE {TABLE}",
        f"ALTER TABLE {TABLE} ADD COLUMN x int",
        f"DROP TABLE {TABLE}",
    ):
        with pytest.raises(pgerr.InsufficientPrivilege):
            loader.execute(statement)
    assert loader.execute(f"DELETE FROM {TABLE} WHERE municipality_name = 'Z'").rowcount == 1


def test_reader_only_selects(conns):
    reader = conns[Profile.READER]
    assert count(reader, TABLE) == BIG_ROWS + TEN_ROWS
    for statement in (
        f"DELETE FROM {TABLE}",
        f"INSERT INTO {TABLE} SELECT * FROM {TABLE} LIMIT 1",
        f"UPDATE {TABLE} SET vehicle_count = 1",
        f"TRUNCATE {TABLE}",
    ):
        with pytest.raises(pgerr.InsufficientPrivilege):
            reader.execute(statement)


def test_transformer_only_selects(conns):
    transformer = conns[Profile.TRANSFORMER]
    assert count(transformer, TABLE) == BIG_ROWS + TEN_ROWS
    for statement in (
        f"DELETE FROM {TABLE}",
        f"INSERT INTO {TABLE} SELECT * FROM {TABLE} LIMIT 1",
        f"UPDATE {TABLE} SET vehicle_count = 1",
        f"TRUNCATE {TABLE}",
    ):
        with pytest.raises(pgerr.InsufficientPrivilege):
            transformer.execute(statement)


# --- table constraints (D99) ----------------------------------------------------------------

_GOOD = {
    "publication_year": 2026,
    "publication_month": 10,
    "department_name": "DEP",
    "municipality_name": "MUNI NUEVO",
    "service_name": "SERV",
    "vehicle_status": "ACTIVO",
    "vehicle_class": "CLASE",
    "registration_year": 2000,
    "vehicle_count": 1,
    "source_system": "mintransporte_runt_parque",
    "source_reference": "raw/p0#row=0",
}


def _insert(conn, load_id, **overrides):
    values = {**_GOOD, **overrides, "load_id": load_id}
    columns = ", ".join(values)
    placeholders = ", ".join(f"%({name})s" for name in values)
    conn.execute(f"INSERT INTO {TABLE} ({columns}) VALUES ({placeholders})", values)


def test_table_columns_are_the_csv_plus_lineage(warehouse):
    cols = [
        r[0]
        for r in warehouse.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'landing' AND table_name = 'vehicle_fleet_snapshot' "
            "ORDER BY ordinal_position"
        )
    ]
    assert cols == [
        "publication_year", "publication_month", "department_name", "municipality_name",
        "service_name", "vehicle_status", "vehicle_class", "registration_year", "vehicle_count",
        "source_system", "source_reference", "load_id",
    ]  # fmt: skip
    pk = warehouse.execute(
        "SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid "
        "AND a.attnum = ANY (i.indkey) WHERE i.indrelid = %s::regclass AND i.indisprimary "
        "ORDER BY array_position(i.indkey::int[], a.attnum::int)",
        (TABLE,),
    ).fetchall()
    assert [r[0] for r in pk] == cols[:8]


@pytest.mark.parametrize(
    "bad",
    [
        {"publication_month": 0},
        {"publication_month": 13},
        {"publication_year": 1999},
        {"publication_year": 2101},
        {"registration_year": 1899},
        {"registration_year": 2027},
        {"vehicle_count": 0},
        {"vehicle_count": -3},
        {"department_name": ""},
        {"municipality_name": "   "},
        {"service_name": " SERV"},
        {"vehicle_status": "ACTIVO "},
        {"vehicle_class": ""},
        {"source_system": "Bad System"},
        {"source_reference": "  "},
    ],
)
def test_table_rejects_bad_rows(warehouse, conns_loaded, bad):
    loader, load_id = conns_loaded
    _insert(loader, load_id)  # the base row is valid
    loader.execute(f"DELETE FROM {TABLE} WHERE municipality_name = 'MUNI NUEVO'")
    with pytest.raises(pgerr.CheckViolation):
        _insert(loader, load_id, **bad)


def test_table_rejects_duplicate_primary_key_and_unknown_load_id(warehouse, conns_loaded):
    loader, load_id = conns_loaded
    _insert(loader, load_id)
    with pytest.raises(pgerr.UniqueViolation):
        _insert(loader, load_id)
    with pytest.raises(pgerr.ForeignKeyViolation):
        _insert(loader, load_id + 10_000, municipality_name="OTRO")


@pytest.fixture
def conns_loaded(warehouse, pg_settings):
    assert load("--publication", "2026-10").exit_code == 0
    load_id = warehouse.execute("SELECT max(load_id) FROM ops.load_run").fetchone()[0]
    loader = connect(pg_settings, Profile.LOADER, autocommit=True)
    yield loader, load_id
    loader.close()

"""`pits load fx-rate` against a real Postgres 17: real migrations, real normalizer artifact.

Each test gets its own database and roles (see conftest). The S3 side is a MemoryRawStore.
"""

from __future__ import annotations

import dataclasses
from contextlib import contextmanager
from datetime import UTC, date, datetime

import fx_load_support as fx
import psycopg
import pytest
from fx_load_support import LAST_DAY, load
from trm_helpers import B3

from pits.ingestion.manifest import sha256_hex
from pits.normalized.manifest import (
    Coverage,
    NormalizedManifest,
    Output,
    compute_input_fingerprint,
)
from pits.warehouse import load_cli
from pits.warehouse.connection import connect
from pits.warehouse.fx_rate_load import LOAD_LOCK_KEY, open_warehouse
from pits.warehouse.migrate import run_migrate
from pits.warehouse.settings import Profile

# Fixtures shared with test_warehouse_lock_pg.py, re-exposed by assignment (pytest uses the name).
base_artifact = fx.base_artifact
store = fx.store
base = fx.base
warehouse = fx.warehouse


def fields(output: str) -> dict[str, str]:
    line = next(line for line in output.splitlines() if line.startswith("outcome="))
    return dict(part.split("=", 1) for part in line.split())


def snapshot(admin):
    rates = admin.execute(
        "SELECT ctid::text, xmin::text, rate_date, rate, source_reference, load_id "
        "FROM landing.fx_rate ORDER BY rate_date"
    ).fetchall()
    runs = admin.execute(
        "SELECT ctid::text, xmin::text, load_id, input_fingerprint, rows_inserted, "
        "rows_updated, rows_deleted FROM ops.load_run ORDER BY load_id"
    ).fetchall()
    return rates, runs


def craft(store, base, transform, *, day=date(2026, 10, 20)):
    """Write a consistent artifact derived from `base` whose CSV lines go through `transform`.

    It carries a later last input (so it is newer than `base`) and a coherent sha256/size.
    """
    manifest = NormalizedManifest.from_json(store.get(base.manifest_key))
    lines = store.get(base.csv_key).decode().splitlines()
    header, body = lines[0], transform(lines[1:])
    csv = ("\n".join([header, *body]) + "\n").encode()
    last = manifest.inputs[-1]
    new_input = dataclasses.replace(
        last,
        batch_id=B3,
        extraction_date=day,
        finished_at=datetime(day.year, day.month, day.day, 12, tzinfo=UTC),
    )
    inputs = (*manifest.inputs[:-1], new_input)
    fingerprint = compute_input_fingerprint(manifest.transform, manifest.raw_bucket, inputs)
    directory = (
        f"fx_rate/source_system=superfinanciera_trm/inputs_until={day.isoformat()}/"
        f"fingerprint={fingerprint}/"
    )
    crafted = dataclasses.replace(
        manifest,
        inputs=inputs,
        baseline_batch_id=B3,
        input_fingerprint=fingerprint,
        coverage=Coverage(
            date.fromisoformat(body[0].split(",")[0]), date.fromisoformat(body[-1].split(",")[0])
        ),
        row_count=len(body),
        output=Output(directory + "fx_rate.csv", sha256_hex(csv), len(csv), "text/csv"),
    )
    store.objects[crafted.output.key] = csv
    store.objects[directory + "manifest.json"] = crafted.to_json()
    return crafted


def count(admin, table):
    return admin.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


# --- happy path and idempotence -------------------------------------------------------------


def test_first_load_inserts_everything(warehouse, base):
    result = load()
    assert result.exit_code == 0, result.output
    out = fields(result.output)
    assert out["outcome"] == "loaded" and out["fingerprint"] == base.fingerprint
    assert (out["rows"], out["inserted"], out["updated"], out["deleted"]) == (
        str(base.rows),
        str(base.rows),
        "0",
        "0",
    )
    assert out["coverage"] == f"1991-12-02..{LAST_DAY.isoformat()}"
    assert out["manifest"] == f"s3://pits-normalized/{base.manifest_key}"
    assert count(warehouse, "landing.fx_rate") == base.rows
    run = warehouse.execute(
        "SELECT load_id, rows_inserted, row_count, input_fingerprint, csv_key, "
        "normalized_manifest->>'input_fingerprint', loader_version FROM ops.load_run"
    ).fetchall()
    assert len(run) == 1 and run[0][1:4] == (base.rows, base.rows, base.fingerprint)
    assert run[0][5] == base.fingerprint and run[0][4] == base.csv_key


def test_second_load_is_a_noop(warehouse, base):
    assert load().exit_code == 0
    before = snapshot(warehouse)
    result = load()
    assert result.exit_code == 0, result.output
    out = fields(result.output)
    assert out["outcome"] == "already_loaded" and out["load_id"] == str(before[1][0][2])
    assert (out["inserted"], out["updated"], out["deleted"]) == ("0", "0", "0")
    assert snapshot(warehouse) == before  # same rows, same ctid and xmin: nothing was written


def test_trimmed_tail_and_corrected_rate_have_exact_counts(warehouse, store, base):
    assert load().exit_code == 0

    def transform(body):
        body = body[:-1]  # drop the last day
        parts = body[-3].split(",")
        parts[3] = "3999.99"  # correct one rate
        body[-3] = ",".join(parts)
        return body

    crafted = craft(store, base, transform)
    result = load()
    assert result.exit_code == 0, result.output
    out = fields(result.output)
    assert out["fingerprint"] == crafted.input_fingerprint and out["outcome"] == "loaded"
    assert (out["inserted"], out["updated"], out["deleted"]) == ("0", "1", "1")
    assert out["rows"] == str(base.rows - 1)
    assert count(warehouse, "landing.fx_rate") == base.rows - 1
    corrected = warehouse.execute(
        "SELECT rate FROM landing.fx_rate WHERE rate_date = %s", (date(2026, 10, 10),)
    ).fetchone()
    assert str(corrected[0]) == "3999.99"
    runs = warehouse.execute(
        "SELECT rows_inserted, rows_updated, rows_deleted FROM ops.load_run ORDER BY load_id"
    ).fetchall()
    assert runs == [(base.rows, 0, 0), (0, 1, 1)]
    assert fields(load().output)["outcome"] == "already_loaded"


def test_regression_is_exit_1(warehouse, store, base):
    craft(store, base, lambda body: body[:-1])
    assert load().exit_code == 0
    # Remove the newest artifact so the selector now offers only the older one.
    for key in [k for k in store.objects if "inputs_until=2026-10-20" in k]:
        del store.objects[key]
    result = load()
    assert result.exit_code == 1 and "older" in result.output
    assert load("--fingerprint", base.fingerprint).exit_code == 0


# --- atomicity ------------------------------------------------------------------------------


def test_failure_after_merge_leaves_tables_untouched(warehouse, store, base, monkeypatch):
    assert load().exit_code == 0
    craft(store, base, lambda body: body[:-1])
    before = snapshot(warehouse)

    def boom(conn):
        raise RuntimeError("injected failure after MERGE")

    @contextmanager
    def factory(settings):
        with open_warehouse(settings, after_merge=boom) as wh:
            yield wh

    monkeypatch.setattr(load_cli, "warehouse_factory", factory)
    result = load()
    assert result.exit_code != 0 and isinstance(result.exception, RuntimeError)
    assert snapshot(warehouse) == before


def test_terminated_backend_is_exit_3_and_retry_loads(warehouse, pg_settings, monkeypatch):
    def kill_own_backend(conn):
        pid = conn.pgconn.backend_pid
        warehouse.execute("SELECT pg_terminate_backend(%s)", (pid,))

    @contextmanager
    def killing_factory(settings):
        with open_warehouse(settings, after_merge=kill_own_backend) as wh:
            yield wh

    monkeypatch.setattr(load_cli, "warehouse_factory", killing_factory)
    result = load()
    assert result.exit_code == 3, result.output
    assert count(warehouse, "landing.fx_rate") == 0 and count(warehouse, "ops.load_run") == 0
    monkeypatch.setattr(load_cli, "warehouse_factory", open_warehouse)
    retry = load()
    assert retry.exit_code == 0 and fields(retry.output)["outcome"] == "loaded"


def test_busy_lock_is_exit_3(warehouse, pg_settings):
    holder = connect(pg_settings, Profile.ADMIN, autocommit=True)
    holder.execute("SELECT pg_advisory_lock(%s)", (LOAD_LOCK_KEY,))
    try:
        result = load()
    finally:
        holder.close()
    assert result.exit_code == 3 and "lock" in result.output
    assert count(warehouse, "ops.load_run") == 0
    assert load().exit_code == 0


def test_rate_zero_with_coherent_sha_is_exit_1_and_rolls_back(warehouse, store, base):
    def transform(body):
        parts = body[100].split(",")
        parts[3] = "0"
        body[100] = ",".join(parts)
        return body

    craft(store, base, transform)
    result = load()
    assert result.exit_code == 1, result.output
    assert count(warehouse, "landing.fx_rate") == 0 and count(warehouse, "ops.load_run") == 0


def test_rows_from_another_source_are_never_overwritten(warehouse, store, base):
    assert load().exit_code == 0
    warehouse.execute(
        "UPDATE landing.fx_rate SET source_system = 'other_source' WHERE rate_date = %s",
        (date(2026, 10, 10),),
    )
    craft(store, base, lambda body: body[:-1])
    before = snapshot(warehouse)
    result = load()
    assert result.exit_code == 1 and "another source" in result.output
    assert snapshot(warehouse) == before


# --- drift and repair -----------------------------------------------------------------------


def test_manual_drift_is_exit_1_and_repair_fixes_it(warehouse, base):
    assert load().exit_code == 0
    warehouse.execute(
        "UPDATE landing.fx_rate SET rate = rate + 1 WHERE rate_date = %s", (date(2026, 10, 10),)
    )
    result = load()
    assert result.exit_code == 1 and "--repair" in result.output
    repaired = load("--repair")
    assert repaired.exit_code == 0, repaired.output
    out = fields(repaired.output)
    assert (out["outcome"], out["inserted"], out["updated"], out["deleted"]) == (
        "loaded",
        "0",
        "1",
        "0",
    )
    assert fields(load().output)["outcome"] == "already_loaded"


def test_deleted_and_extra_rows_are_repaired(warehouse, base):
    assert load().exit_code == 0
    warehouse.execute("DELETE FROM landing.fx_rate WHERE rate_date = %s", (date(2026, 10, 12),))
    assert load().exit_code == 1
    out = fields(load("--repair").output)
    assert (out["inserted"], out["updated"], out["deleted"]) == ("1", "0", "0")
    # A tail row beyond the manifest coverage (same source) is deleted by the repair.
    warehouse.execute(
        "INSERT INTO landing.fx_rate SELECT %s, currency_from, currency_to, rate, source_system, "
        "source_reference, load_id FROM landing.fx_rate WHERE rate_date = %s",
        (date(2026, 10, 14), LAST_DAY),
    )
    assert load().exit_code == 1
    out = fields(load("--repair").output)
    assert (out["inserted"], out["updated"], out["deleted"]) == ("0", "0", "1")
    assert count(warehouse, "landing.fx_rate") == base.rows


# --- credentials ----------------------------------------------------------------------------


def test_wrong_password_is_exit_1_and_never_printed(warehouse, pg_settings, monkeypatch):
    wrong = "wrong-password-sentinel-0123456789"
    bad = dataclasses.replace(pg_settings, loader_password=wrong)
    monkeypatch.setattr(load_cli, "settings_factory", lambda env: bad)
    result = load()
    assert result.exit_code == 1, result.output
    for secret in (wrong, pg_settings.loader_password, pg_settings.admin_password):
        assert secret not in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_passwords_never_appear_in_output(warehouse, pg_settings):
    result = load()
    assert result.exit_code == 0
    for secret in (pg_settings.loader_password, pg_settings.reader_password):
        assert secret not in result.output


def test_connect_error_chain_has_no_pgconn(pg_settings):
    bad = dataclasses.replace(pg_settings, loader_password="wrong-password-0123456789")
    run_migrate(pg_settings)
    with pytest.raises(Exception) as info:  # noqa: B017 - typed WarehousePermanentError
        connect(bad, Profile.LOADER)
    assert info.value.__context__ is None
    assert not isinstance(info.value, psycopg.Error)

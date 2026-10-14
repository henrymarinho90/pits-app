"""Offline tests for pits.warehouse.brand_fleet_load with a fake BrandFleetWarehouse."""

from __future__ import annotations

import csv
import hashlib
import io
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from brand_fleet_artifact_support import DAY, RAW_BUCKET, build_raw_and_normalized
from brand_fleet_support import BOYACA, RISARALDA

from pits.ingestion.raw_store import MemoryRawStore, RawStoreTransientError
from pits.normalized.brand_fleet_reader import select_artifact
from pits.warehouse.brand_fleet_load import (
    check_digest,
    check_summary,
    load_brand_fleet,
    plan_step,
    reconstruct_digest,
)
from pits.warehouse.divipola_load import ApplyResult
from pits.warehouse.errors import WarehousePermanentError, WarehouseTransientError
from pits.warehouse.fx_rate_load import LastRun, Outcome, Step


class FakeSession:
    def __init__(self, wh):
        self.wh = wh

    def try_lock(self):
        self.wh.calls.append("lock")
        return self.wh.lock_ok

    def last_run(self, source_system):
        self.wh.calls.append(f"last_run:{source_system}")
        return self.wh.last

    def verify(self, selected):
        self.wh.calls.append("verify")
        return list(self.wh.verify_problems.pop(0)) if self.wh.verify_problems else []

    def apply(self, selected, csv_bytes, loader_version):
        self.wh.calls.append("apply")
        self.wh.applied.append((selected.manifest.input_fingerprint, loader_version, csv_bytes))
        return ApplyResult(load_id=41, inserted=4, deleted=2)


class FakeWarehouse:
    def __init__(self, last=None, lock_ok=True, verify_problems=()):
        self.last = last
        self.lock_ok = lock_ok
        self.verify_problems = [list(p) for p in verify_problems]
        self.calls: list[str] = []
        self.applied: list = []
        self.transactions: list[str] = []

    @contextmanager
    def transaction(self):
        try:
            yield FakeSession(self)
        except BaseException:
            self.transactions.append("rollback")
            raise
        self.transactions.append("commit")


@pytest.fixture
def env():
    return build_raw_and_normalized()


def last_run_for(result, **overrides):
    base = {
        "load_id": 7,
        "input_fingerprint": result.fingerprint,
        "last_input_batch_id": result.batch_id,
        "last_input_extraction_date": DAY,
        "last_input_finished_at": datetime(2026, 10, 14, 12, tzinfo=UTC),
    }
    return LastRun(**{**base, **overrides})


def run(store, wh, source=BOYACA, **kwargs):
    return load_brand_fleet(store, wh, RAW_BUCKET, source, loader_version="9.9.9", **kwargs)


# --- flow -----------------------------------------------------------------------------------


def test_never_loaded_applies_and_verifies_in_one_transaction(env):
    _, norm, results = env
    result = results["boyaca"]
    wh = FakeWarehouse()
    out = run(norm, wh)
    assert wh.calls == ["lock", f"last_run:{BOYACA.source_system}", "apply", "verify"]
    assert wh.transactions == ["commit"]
    assert (out.outcome, out.load_id, out.inserted, out.deleted) == (Outcome.LOADED, 41, 4, 2)
    assert out.fingerprint == result.fingerprint and out.rows == result.rows
    assert out.vehicles == result.vehicles == 6
    assert out.source_system == BOYACA.source_system
    assert out.rows_updated == result.rows_updated and out.manifest_key == result.manifest_key
    fingerprint, version, body = wh.applied[0]
    assert (fingerprint, version) == (result.fingerprint, "9.9.9")
    assert body.startswith(b"vehicle_class,")


def test_last_run_is_asked_per_source_system(env):
    _, norm, results = env
    wh = FakeWarehouse()
    out = run(norm, wh, RISARALDA)
    assert wh.calls[1] == f"last_run:{RISARALDA.source_system}"
    assert out.fingerprint == results["risaralda"].fingerprint


def test_same_fingerprint_consistent_is_already_loaded_without_writes_or_csv_reads(env):
    _, norm, results = env
    gets: list[str] = []

    class Spy(MemoryRawStore):
        def get(self, key):
            gets.append(key)
            return super().get(key)

    spy = Spy()
    spy.objects = dict(norm.objects)
    wh = FakeWarehouse(last=last_run_for(results["boyaca"]))
    out = run(spy, wh)
    assert out.outcome is Outcome.ALREADY_LOADED and out.load_id == 7
    assert (out.inserted, out.deleted) == (0, 0)
    assert wh.calls == ["lock", f"last_run:{BOYACA.source_system}", "verify"]
    assert wh.applied == []
    assert not any(k.endswith(".csv") for k in gets)


def test_same_fingerprint_with_drift_is_permanent_unless_repair(env):
    _, norm, results = env
    last = last_run_for(results["boyaca"])
    wh = FakeWarehouse(last=last, verify_problems=[["row count 2 != manifest 4"]])
    with pytest.raises(WarehousePermanentError, match="drifted.*--repair.*row count 2"):
        run(norm, wh)
    assert wh.applied == [] and wh.transactions == ["rollback"]

    wh = FakeWarehouse(last=last, verify_problems=[["drift"], []])
    out = run(norm, wh, repair=True)
    assert out.outcome is Outcome.LOADED
    assert wh.calls[2:] == ["verify", "apply", "verify"]


def test_forced_fingerprint_bypasses_the_regression_guard(env):
    _, norm, results = env
    first = results["boyaca"]
    newer_last = last_run_for(
        first, input_fingerprint="f" * 64, last_input_extraction_date=DAY.replace(day=28)
    )
    wh = FakeWarehouse(last=newer_last)
    out = run(norm, wh, fingerprint=first.fingerprint)
    assert out.outcome is Outcome.LOADED and wh.calls[-2:] == ["apply", "verify"]


def test_regression_without_force_is_permanent(env):
    _, norm, results = env
    newer_last = last_run_for(
        results["boyaca"],
        input_fingerprint="f" * 64,
        last_input_extraction_date=DAY.replace(day=28),
    )
    wh = FakeWarehouse(last=newer_last)
    with pytest.raises(WarehousePermanentError, match="older than the loaded"):
        run(norm, wh)
    assert wh.applied == [] and wh.transactions == ["rollback"]


def test_busy_lock_is_transient(env):
    _, norm, _ = env
    wh = FakeWarehouse(lock_ok=False)
    with pytest.raises(WarehouseTransientError, match="advisory lock"):
        run(norm, wh)
    assert wh.calls == ["lock"] and wh.transactions == ["rollback"]


def test_verification_failure_after_load_rolls_back(env):
    _, norm, _ = env
    wh = FakeWarehouse(verify_problems=[["rebuilt CSV sha256 differs from manifest"]])
    with pytest.raises(WarehousePermanentError, match="verification failed after load"):
        run(norm, wh)
    assert wh.transactions == ["rollback"]


def test_read_errors_become_warehouse_errors(env):
    _, norm, _ = env
    with pytest.raises(WarehousePermanentError, match="No committed"):
        run(MemoryRawStore(), FakeWarehouse())

    def boom(prefix):
        raise RawStoreTransientError("simulated")

    norm.list_prefixes = boom
    with pytest.raises(WarehouseTransientError):
        run(norm, FakeWarehouse())


def test_tampered_csv_is_permanent_before_any_write(env):
    _, norm, _ = env
    key = select_artifact(norm, RAW_BUCKET, BOYACA).csv_key
    norm.objects[key] = norm.objects[key] + b"x"
    wh = FakeWarehouse()
    with pytest.raises(WarehousePermanentError, match="size"):
        run(norm, wh)
    assert wh.applied == [] and wh.transactions == ["rollback"]


# --- pure logic -----------------------------------------------------------------------------


def test_plan_step_table(env):
    _, norm, results = env
    result = results["boyaca"]
    selected = select_artifact(norm, RAW_BUCKET, BOYACA)
    assert plan_step(selected, None, forced=False) is Step.LOAD
    assert plan_step(selected, last_run_for(result), forced=False) is Step.VERIFY
    older = last_run_for(
        result, input_fingerprint="e" * 64, last_input_extraction_date=DAY.replace(day=28)
    )
    assert plan_step(selected, older, forced=False) is Step.REGRESSION
    assert plan_step(selected, older, forced=True) is Step.LOAD
    newer = last_run_for(
        result, input_fingerprint="e" * 64, last_input_extraction_date=DAY.replace(day=1)
    )
    assert plan_step(selected, newer, forced=False) is Step.LOAD


def test_reconstruct_digest_equals_the_artifact_digest(env):
    _, norm, _ = env
    selected = select_artifact(norm, RAW_BUCKET, BOYACA)
    body = norm.get(selected.csv_key)
    rows = list(csv.reader(io.StringIO(body.decode("utf-8"))))[1:]
    sha256, size = reconstruct_digest(rows)
    assert (sha256, size) == (hashlib.sha256(body).hexdigest(), len(body))
    assert check_digest(selected, sha256, size) == []
    m = selected.manifest
    assert check_summary(selected, count=m.row_count, vehicles=m.vehicle_total, other_dates=0) == []


def test_risaralda_digest_with_empty_service_and_status(env):
    _, norm, _ = env
    selected = select_artifact(norm, RAW_BUCKET, RISARALDA)
    body = norm.get(selected.csv_key)
    rows = list(csv.reader(io.StringIO(body.decode("utf-8"))))[1:]
    assert all(r[3] == "" and r[4] == "" for r in rows)
    assert reconstruct_digest(rows) == (hashlib.sha256(body).hexdigest(), len(body))


def test_digest_and_summary_report_differences(env):
    _, norm, _ = env
    selected = select_artifact(norm, RAW_BUCKET, BOYACA)
    rows = list(csv.reader(io.StringIO(norm.get(selected.csv_key).decode("utf-8"))))[1:]
    sha256, size = reconstruct_digest(rows[:-1])
    assert check_digest(selected, sha256, size) == [
        "rebuilt CSV size differs from manifest",
        "rebuilt CSV sha256 differs from manifest",
    ]
    m = selected.manifest
    assert check_summary(
        selected, count=m.row_count - 1, vehicles=m.vehicle_total, other_dates=0
    ) == [f"row count {m.row_count - 1} != manifest {m.row_count}"]
    assert check_summary(selected, count=m.row_count, vehicles=1, other_dates=2) == [
        f"vehicle total 1 != manifest {m.vehicle_total}",
        "2 rows have a rows_updated other than the manifest's",
    ]

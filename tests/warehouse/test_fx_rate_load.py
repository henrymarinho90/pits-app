"""Offline tests for pits.warehouse.fx_rate_load with a fake FxRateWarehouse."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from trm_helpers import B1, B2, put_raw_batch, raw_row

from pits.ingestion.raw_store import MemoryRawStore, RawStoreTransientError
from pits.normalized.fx_rate_csv import FxRateCsvError, serialize_fx_rate
from pits.normalized.reader import select_artifact
from pits.sources.trm.contract import BACKFILL_FROM
from pits.sources.trm.normalize import normalize_trm
from pits.sources.trm.replay import FxDay
from pits.warehouse.errors import WarehousePermanentError, WarehouseTransientError
from pits.warehouse.fx_rate_load import (
    ApplyResult,
    LastRun,
    Outcome,
    Step,
    check_summary,
    load_fx_rate,
    plan_step,
    reconstruct_digest,
)

RAW_BUCKET = "pits-raw"
DAY1 = date(2026, 10, 9)
DAY2 = date(2026, 10, 10)


def _build(extra_incremental: bool = False):
    raw = MemoryRawStore()
    norm = MemoryRawStore()
    put_raw_batch(
        raw,
        B1,
        DAY1,
        "full",
        [
            raw_row(BACKFILL_FROM, date(2026, 10, 9), "3000.5"),
            raw_row(date(2026, 10, 10), date(2026, 10, 13), "3194.44"),
        ],
    )
    first = normalize_trm(raw, norm, raw_bucket=RAW_BUCKET)
    if not extra_incremental:
        return norm, first, None
    put_raw_batch(
        raw,
        B2,
        DAY2,
        "incremental",
        [raw_row(date(2026, 10, 14), date(2026, 10, 14), "3200")],
        from_exclusive=date(2026, 10, 10),
    )
    return norm, first, normalize_trm(raw, norm, raw_bucket=RAW_BUCKET)


class FakeSession:
    def __init__(self, wh):
        self.wh = wh

    def try_lock(self):
        self.wh.calls.append("lock")
        return self.wh.lock_ok

    def last_run(self):
        self.wh.calls.append("last_run")
        return self.wh.last

    def verify(self, selected):
        self.wh.calls.append("verify")
        return list(self.wh.verify_problems.pop(0)) if self.wh.verify_problems else []

    def apply(self, artifact, loader_version):
        self.wh.calls.append("apply")
        self.wh.applied.append((artifact, loader_version))
        return ApplyResult(load_id=42, inserted=3, updated=2, deleted=1)


class FakeWarehouse:
    def __init__(self, last=None, lock_ok=True, verify_problems=()):
        self.last, self.lock_ok = last, lock_ok
        self.verify_problems = [list(p) for p in verify_problems]
        self.calls: list[str] = []
        self.applied: list = []
        self.committed = self.rolled_back = False

    @contextmanager
    def transaction(self):
        try:
            yield FakeSession(self)
        except BaseException:
            self.rolled_back = True
            raise
        self.committed = True


def last_run_for(result, **overrides):
    """LastRun equal to the artifact the normalizer just produced."""
    base = {
        "load_id": 7,
        "input_fingerprint": result.fingerprint,
        "last_input_batch_id": B1,
        "last_input_extraction_date": DAY1,
        "last_input_finished_at": datetime(2026, 10, 9, 12, 0, 30, tzinfo=UTC),
    }
    return LastRun(**{**base, **overrides})


def run(store, wh, **kwargs):
    return load_fx_rate(store, wh, RAW_BUCKET, loader_version="9.9.9", **kwargs)


# --- decision table ------------------------------------------------------------------------


def test_never_loaded_loads_and_verifies_after():
    norm, first, _ = _build()
    wh = FakeWarehouse()
    result = run(norm, wh)
    assert wh.calls == ["lock", "last_run", "apply", "verify"]
    assert wh.committed and not wh.rolled_back
    assert (result.outcome, result.load_id) == (Outcome.LOADED, 42)
    assert (result.inserted, result.updated, result.deleted) == (3, 2, 1)
    assert result.fingerprint == first.fingerprint and result.rows == first.rows
    assert result.manifest_key == first.manifest_key
    assert (result.coverage_from, result.coverage_to) == (BACKFILL_FROM, date(2026, 10, 13))
    assert wh.applied[0][1] == "9.9.9"
    assert wh.applied[0][0].csv_bytes == norm.get(first.csv_key)


def test_same_fingerprint_consistent_is_already_loaded_without_writes():
    norm, first, _ = _build()
    gets: list[str] = []

    class Spy(MemoryRawStore):
        def get(self, key):
            gets.append(key)
            return super().get(key)

    spy = Spy()
    spy.objects = norm.objects
    wh = FakeWarehouse(last=last_run_for(first))
    result = run(spy, wh)
    assert result.outcome is Outcome.ALREADY_LOADED and result.load_id == 7
    assert (result.inserted, result.updated, result.deleted) == (0, 0, 0)
    assert wh.calls == ["lock", "last_run", "verify"] and wh.applied == []
    assert not any(key.endswith(".csv") for key in gets)  # the CSV is not even downloaded


def test_same_fingerprint_drift_is_permanent_without_repair():
    norm, first, _ = _build()
    wh = FakeWarehouse(last=last_run_for(first), verify_problems=[["row count 1 != manifest 9"]])
    with pytest.raises(WarehousePermanentError, match="--repair"):
        run(norm, wh)
    assert wh.applied == [] and wh.rolled_back


def test_same_fingerprint_drift_with_repair_reloads():
    norm, first, _ = _build()
    wh = FakeWarehouse(last=last_run_for(first), verify_problems=[["drift"], []])
    result = run(norm, wh, repair=True)
    assert result.outcome is Outcome.LOADED
    assert wh.calls == ["lock", "last_run", "verify", "apply", "verify"]


def test_repair_is_ignored_when_nothing_drifted():
    norm, first, _ = _build()
    wh = FakeWarehouse(last=last_run_for(first))
    assert run(norm, wh, repair=True).outcome is Outcome.ALREADY_LOADED
    assert wh.applied == []


def test_artifact_older_than_loaded_is_a_regression():
    norm, first, _ = _build()
    newer = last_run_for(
        first, input_fingerprint="f" * 64, last_input_extraction_date=date(2026, 10, 20)
    )
    wh = FakeWarehouse(last=newer)
    with pytest.raises(WarehousePermanentError, match="older"):
        run(norm, wh)
    assert wh.applied == [] and wh.rolled_back


def test_regression_is_bypassed_with_fingerprint():
    norm, first, _ = _build()
    newer = last_run_for(
        first, input_fingerprint="f" * 64, last_input_extraction_date=date(2026, 10, 20)
    )
    wh = FakeWarehouse(last=newer)
    result = run(norm, wh, fingerprint=first.fingerprint)
    assert result.outcome is Outcome.LOADED and len(wh.applied) == 1


def test_newer_artifact_replaces_the_loaded_one():
    norm, first, second = _build(extra_incremental=True)
    wh = FakeWarehouse(last=last_run_for(first))
    result = run(norm, wh)
    assert result.fingerprint == second.fingerprint and result.outcome is Outcome.LOADED


def test_plan_step_table():
    norm, first, second = _build(extra_incremental=True)
    old, new = (select_artifact(norm, RAW_BUCKET, r.fingerprint) for r in (first, second))
    loaded_old, loaded_new = (
        last_run_for(first),
        last_run_for(
            second,
            last_input_batch_id=B2,
            last_input_extraction_date=DAY2,
            last_input_finished_at=new.last_input.finished_at,
        ),
    )
    assert plan_step(new, None, forced=False) is Step.LOAD
    assert plan_step(old, loaded_old, forced=False) is Step.VERIFY
    assert plan_step(new, loaded_old, forced=False) is Step.LOAD
    assert plan_step(old, loaded_new, forced=False) is Step.REGRESSION
    assert plan_step(old, loaded_new, forced=True) is Step.LOAD
    assert plan_step(new, loaded_new, forced=True) is Step.VERIFY
    # Equal commit order but a different fingerprint is not a regression.
    same_order = last_run_for(first, input_fingerprint="e" * 64)
    assert plan_step(old, same_order, forced=False) is Step.LOAD


def test_lock_busy_is_transient_and_nothing_else_runs():
    norm, *_ = _build()
    wh = FakeWarehouse(lock_ok=False)
    with pytest.raises(WarehouseTransientError, match="lock"):
        run(norm, wh)
    assert wh.calls == ["lock"] and wh.rolled_back


def test_verification_failure_after_load_rolls_back():
    norm, *_ = _build()
    wh = FakeWarehouse(verify_problems=[["rebuilt CSV sha256 differs from manifest"]])
    with pytest.raises(WarehousePermanentError, match="Verification failed"):
        run(norm, wh)
    assert wh.calls[-2:] == ["apply", "verify"] and wh.rolled_back and not wh.committed


# --- reader error mapping -------------------------------------------------------------------


def test_selection_errors_are_permanent():
    with pytest.raises(WarehousePermanentError, match="No committed"):
        run(MemoryRawStore(), FakeWarehouse())


def test_transient_store_error_is_transient():
    norm, *_ = _build()

    class Down(MemoryRawStore):
        def list_prefixes(self, prefix):
            raise RawStoreTransientError("timeout")

    with pytest.raises(WarehouseTransientError):
        run(Down(), FakeWarehouse())


def test_csv_hash_mismatch_is_permanent_and_rolls_back():
    norm, first, _ = _build()
    data = bytearray(norm.get(first.csv_key))
    data[-2] ^= 1
    norm.objects[first.csv_key] = bytes(data)
    wh = FakeWarehouse()
    with pytest.raises(WarehousePermanentError, match="sha256"):
        run(norm, wh)
    assert wh.applied == [] and wh.rolled_back


def test_csv_download_failure_is_transient():
    norm, first, _ = _build()

    class FlakyCsv(MemoryRawStore):
        def get(self, key):
            if key.endswith(".csv"):
                raise RawStoreTransientError("reset")
            return super().get(key)

    flaky = FlakyCsv()
    flaky.objects = norm.objects
    with pytest.raises(WarehouseTransientError):
        run(flaky, FakeWarehouse())


# --- reconstruction -------------------------------------------------------------------------


def test_reconstruct_digest_equals_serialize_fx_rate():
    days = [
        FxDay(date(2026, 1, 1), Decimal("3194.440"), "superfinanciera_trm/a#row=0"),
        FxDay(date(2026, 1, 2), Decimal("4000"), "superfinanciera_trm/a#row=1"),
        FxDay(date(2026, 1, 3), Decimal("635.7"), "superfinanciera_trm/a#row=2"),
        FxDay(date(2026, 1, 4), Decimal("0.0000001"), "superfinanciera_trm/a#row=3"),
    ]
    expected = serialize_fx_rate(days)
    rows = [(d.rate_date, "USD", "COP", d.rate, d.source_reference) for d in days]
    sha256, size = reconstruct_digest(rows)
    assert (sha256, size) == (hashlib.sha256(expected).hexdigest(), len(expected))


def test_reconstruct_digest_of_the_real_artifact():
    norm, first, _ = _build()
    selected = select_artifact(norm, RAW_BUCKET)
    lines = norm.get(first.csv_key).decode().splitlines()[1:]
    rows = []
    for line in lines:
        rate_date, cf, ct, rate, ref = line.split(",")
        rows.append((date.fromisoformat(rate_date), cf, ct, Decimal(rate), ref))
    sha256, size = reconstruct_digest(rows)
    assert (sha256, size) == (selected.manifest.output.sha256, selected.manifest.output.size_bytes)


def test_reconstruct_digest_rejects_unrepresentable_rows():
    row = (date(2026, 1, 1), "USD", "COP", Decimal("1"), "ref")
    with pytest.raises(FxRateCsvError):
        reconstruct_digest([(date(2026, 1, 1), "EUR", "COP", Decimal("1"), "ref")])
    with pytest.raises(FxRateCsvError):
        reconstruct_digest([row, row])
    with pytest.raises(FxRateCsvError):
        reconstruct_digest([(date(2026, 1, 1), "USD", "COP", Decimal("0"), "ref")])
    with pytest.raises(FxRateCsvError):
        reconstruct_digest([(date(2026, 1, 1), "USD", "COP", Decimal("NaN"), "ref")])


def test_check_summary():
    norm, first, _ = _build()
    del first
    selected = select_artifact(norm, RAW_BUCKET)
    m = selected.manifest
    ok = check_summary(
        selected, count=m.row_count, min_date=m.coverage.from_date, max_date=m.coverage.to_date
    )
    assert ok == []
    bad = check_summary(selected, count=m.row_count - 1, min_date=date(2000, 1, 1), max_date=None)
    assert len(bad) >= 3
    gap = check_summary(
        selected,
        count=m.row_count - 1,
        min_date=m.coverage.from_date,
        max_date=m.coverage.to_date,
    )
    assert any("one row per day" in p for p in gap)

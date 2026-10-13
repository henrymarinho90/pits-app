"""Offline tests for pits.warehouse.vehicle_fleet_load with a fake FleetWarehouse."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, date, datetime

import pytest
from fleet_artifact_support import (
    DAY,
    RAW_BUCKET,
    add_newer_batch,
    build_raw_and_normalized,
    tricky_rows,
)

from pits.ingestion.raw_store import MemoryRawStore, RawStoreTransientError
from pits.normalized.fleet_csv import FleetPart, logical_content, serialize_fleet
from pits.normalized.fleet_reader import select_artifacts
from pits.sources.runt.parse import parse_page
from pits.warehouse.errors import WarehousePermanentError, WarehouseTransientError
from pits.warehouse.fx_rate_load import LastRun, Outcome, Step
from pits.warehouse.vehicle_fleet_load import (
    ApplyResult,
    check_digest,
    check_summary,
    load_vehicle_fleet,
    plan_step,
    reconstruct_digest,
)


class FakeSession:
    def __init__(self, wh):
        self.wh = wh

    def try_lock(self):
        self.wh.calls.append("lock")
        return self.wh.lock_ok

    def last_run(self, first_day):
        self.wh.calls.append(f"last_run:{first_day.isoformat()}")
        return self.wh.last.get(first_day.isoformat())

    def verify(self, selected):
        self.wh.calls.append(f"verify:{selected.publication}")
        return list(self.wh.verify_problems.pop(0)) if self.wh.verify_problems else []

    def apply(self, selected, parts, loader_version):
        self.wh.calls.append(f"apply:{selected.publication}")
        consumed = list(parts)  # the lazy reader runs here, inside the transaction
        self.wh.applied.append((selected.publication, loader_version, consumed))
        return ApplyResult(load_id=40 + len(self.wh.applied), inserted=3, deleted=1)


class FakeWarehouse:
    def __init__(self, last=None, lock_ok=True, verify_problems=()):
        self.last = last or {}
        self.lock_ok = lock_ok
        self.verify_problems = [list(p) for p in verify_problems]
        self.calls: list[str] = []
        self.applied: list = []
        self.transactions: list[str] = []  # "commit" / "rollback" per transaction

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
        "last_input_finished_at": datetime(2026, 10, 12, 12, tzinfo=UTC),
    }
    return LastRun(**{**base, **overrides})


def run(store, wh, **kwargs):
    return list(load_vehicle_fleet(store, wh, RAW_BUCKET, loader_version="9.9.9", **kwargs))


# --- flow -----------------------------------------------------------------------------------


def test_never_loaded_loads_each_publication_in_its_own_transaction_ascending(env):
    _, norm, results = env
    wh = FakeWarehouse()
    out = run(norm, wh)
    assert wh.calls == [
        "lock",
        "last_run:2026-09-01",
        "apply:2026-09",
        "verify:2026-09",
        "lock",
        "last_run:2026-10-01",
        "apply:2026-10",
        "verify:2026-10",
    ]
    assert wh.transactions == ["commit", "commit"]
    assert [r.publication for r in out] == ["2026-09", "2026-10"]
    first = out[0]
    assert (first.outcome, first.load_id, first.updated) == (Outcome.LOADED, 41, 0)
    assert (first.inserted, first.deleted) == (3, 1)
    assert first.fingerprint == results["2026-09"].fingerprint
    assert first.rows == results["2026-09"].rows
    assert first.manifest_key == results["2026-09"].manifest_key
    assert wh.applied[0][1] == "9.9.9"
    assert len(wh.applied[0][2]) == results["2026-09"].parts  # every part reached the session


def test_publication_filter_touches_only_that_publication(env):
    _, norm, _ = env
    wh = FakeWarehouse()
    out = run(norm, wh, publication="2026-10")
    assert [r.publication for r in out] == ["2026-10"]
    assert all("2026-09" not in call for call in wh.calls)


def test_same_fingerprint_consistent_is_already_loaded_without_writes_or_part_reads(env):
    _, norm, results = env
    gets: list[str] = []

    class Spy(MemoryRawStore):
        def get(self, key):
            gets.append(key)
            return super().get(key)

    spy = Spy()
    spy.objects = norm.objects
    wh = FakeWarehouse(last={"2026-10-01": last_run_for(results["2026-10"])})
    (result,) = run(spy, wh, publication="2026-10")
    assert result.outcome is Outcome.ALREADY_LOADED and result.load_id == 7
    assert (result.inserted, result.updated, result.deleted) == (0, 0, 0)
    assert wh.calls == ["lock", "last_run:2026-10-01", "verify:2026-10"] and wh.applied == []
    assert not any("part-" in key for key in gets)


def test_drift_without_repair_is_permanent_and_rolls_back(env):
    _, norm, results = env
    wh = FakeWarehouse(
        last={"2026-10-01": last_run_for(results["2026-10"])},
        verify_problems=[["row count 1 != manifest 9"]],
    )
    with pytest.raises(WarehousePermanentError, match="--repair"):
        run(norm, wh, publication="2026-10")
    assert wh.applied == [] and wh.transactions == ["rollback"]


def test_drift_with_repair_reloads_and_ignored_when_consistent(env):
    _, norm, results = env
    last = {"2026-10-01": last_run_for(results["2026-10"])}
    wh = FakeWarehouse(last=last, verify_problems=[["drift"], []])
    (result,) = run(norm, wh, publication="2026-10", repair=True)
    assert result.outcome is Outcome.LOADED
    assert wh.calls[2:] == ["verify:2026-10", "apply:2026-10", "verify:2026-10"]
    consistent = FakeWarehouse(last=last)
    assert run(norm, consistent, publication="2026-10", repair=True)[0].outcome is (
        Outcome.ALREADY_LOADED
    )


def test_older_artifact_than_loaded_is_a_regression_unless_forced(env):
    _, norm, results = env
    newer = last_run_for(
        results["2026-10"],
        input_fingerprint="f" * 64,
        last_input_extraction_date=date(2026, 10, 20),
    )
    wh = FakeWarehouse(last={"2026-10-01": newer})
    with pytest.raises(WarehousePermanentError, match="older"):
        run(norm, wh, publication="2026-10")
    assert wh.applied == [] and wh.transactions == ["rollback"]
    forced = FakeWarehouse(last={"2026-10-01": newer})
    (result,) = run(norm, forced, fingerprint=results["2026-10"].fingerprint)
    assert result.outcome is Outcome.LOADED


def test_failure_in_the_second_publication_keeps_the_first_committed(env):
    _, norm, _ = env
    wh = FakeWarehouse(verify_problems=[[], ["rebuilt CSV sha256 differs from manifest"]])
    out = []
    with pytest.raises(WarehousePermanentError, match="2026-10.*verification failed"):
        for result in load_vehicle_fleet(norm, wh, RAW_BUCKET, loader_version="x"):
            out.append(result)
    assert [r.publication for r in out] == ["2026-09"]
    assert wh.transactions == ["commit", "rollback"]


def test_newer_batch_replaces_the_loaded_one(env):
    raw, norm, results = env
    newer = add_newer_batch(raw, norm, (2026, 10), tricky_rows(year=2026, month=10)[:4])
    wh = FakeWarehouse(last={"2026-10-01": last_run_for(results["2026-10"])})
    (result,) = run(norm, wh, publication="2026-10")
    assert result.fingerprint == newer.fingerprint and result.outcome is Outcome.LOADED


def test_lock_busy_is_transient_and_nothing_else_runs(env):
    _, norm, _ = env
    wh = FakeWarehouse(lock_ok=False)
    with pytest.raises(WarehouseTransientError, match="lock"):
        run(norm, wh)
    assert wh.calls == ["lock"] and wh.transactions == ["rollback"]


# --- reader error mapping -------------------------------------------------------------------


def test_selection_errors_are_permanent_and_transient_ones_transient():
    with pytest.raises(WarehousePermanentError, match="No committed"):
        run(MemoryRawStore(), FakeWarehouse())

    class Down(MemoryRawStore):
        def list_prefixes(self, prefix):
            raise RawStoreTransientError("timeout")

    with pytest.raises(WarehouseTransientError):
        run(Down(), FakeWarehouse())


def test_part_hash_mismatch_is_permanent_and_rolls_back(env):
    _, norm, results = env
    (ten,) = select_artifacts(norm, RAW_BUCKET, publication="2026-10")
    key = ten.manifest.parts[0].key
    data = bytearray(norm.get(key))
    data[-2] ^= 1
    norm.objects[key] = bytes(data)
    wh = FakeWarehouse()
    with pytest.raises(WarehousePermanentError, match="sha256"):
        run(norm, wh, publication="2026-10")
    assert wh.transactions == ["rollback"]


def test_part_download_failure_is_transient(env):
    _, norm, _ = env

    class Flaky(MemoryRawStore):
        def get(self, key):
            if "part-" in key:
                raise RawStoreTransientError("reset")
            return super().get(key)

    flaky = Flaky()
    flaky.objects = norm.objects
    wh = FakeWarehouse()
    with pytest.raises(WarehouseTransientError):
        run(flaky, wh, publication="2026-10")
    assert wh.transactions == ["rollback"]


# --- decision table and checks ---------------------------------------------------------------


def test_plan_step_table(env):
    raw, norm, results = env
    newer_result = add_newer_batch(raw, norm, (2026, 10), tricky_rows(year=2026, month=10)[:4])
    old, new = (
        select_artifacts(norm, RAW_BUCKET, fingerprint=r.fingerprint)[0]
        for r in (results["2026-10"], newer_result)
    )
    loaded_old = last_run_for(results["2026-10"])
    loaded_new = last_run_for(
        newer_result,
        last_input_extraction_date=new.input_ref.extraction_date,
        last_input_finished_at=new.input_ref.finished_at,
        last_input_batch_id=new.input_ref.batch_id,
    )
    assert plan_step(new, None, forced=False) is Step.LOAD
    assert plan_step(old, loaded_old, forced=False) is Step.VERIFY
    assert plan_step(new, loaded_old, forced=False) is Step.LOAD
    assert plan_step(old, loaded_new, forced=False) is Step.REGRESSION
    assert plan_step(old, loaded_new, forced=True) is Step.LOAD
    assert plan_step(new, loaded_new, forced=True) is Step.VERIFY
    same_order = last_run_for(results["2026-10"], input_fingerprint="e" * 64)
    assert plan_step(old, same_order, forced=False) is Step.LOAD


def test_check_summary_and_digest_report_each_difference(env):
    _, norm, _ = env
    (ten,) = select_artifacts(norm, RAW_BUCKET, publication="2026-10")
    m = ten.manifest
    assert check_summary(ten, count=m.row_count, vehicle_total=m.vehicle_count_total) == []
    problems = check_summary(ten, count=m.row_count - 1, vehicle_total=m.vehicle_count_total + 1)
    assert len(problems) == 2
    assert check_digest(ten, m.content_sha256, m.content_size_bytes) == []
    assert len(check_digest(ten, "0" * 64, m.content_size_bytes + 1)) == 2


# --- reconstruction -------------------------------------------------------------------------


def test_reconstruct_digest_equals_the_logical_content_of_the_serializer():
    """Quoting, accents and ordering must match serialize_fleet byte for byte."""
    page = tricky_rows(year=2026, month=10)
    records = parse_page(page, page_key="raw/p0", page_index=0, publication=(2026, 10))
    records.sort()
    keys = ["raw/p0"]
    parts: list[FleetPart] = serialize_fleet(records, keys, max_rows=4)
    assert len(parts) > 1
    expected = logical_content(parts)
    rows = [(*r[:9], f"{keys[r[9]]}#row={r[10]}") for r in records]
    assert reconstruct_digest(rows) == expected
    assert reconstruct_digest(reversed(rows)) != expected  # order matters

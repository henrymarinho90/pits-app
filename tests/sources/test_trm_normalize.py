"""Offline tests for pits.sources.trm.normalize (MemoryRawStore, no SODA)."""

from __future__ import annotations

import inspect
import random
from datetime import UTC, date, datetime, timedelta

import pytest
from trm_helpers import B1, B2, B3, put_raw_batch, raw_row

from pits.ingestion.manifest import sha256_hex
from pits.ingestion.raw_store import (
    MemoryRawStore,
    PutOutcome,
    RawObjectConflictError,
    RawStoreTransientError,
)
from pits.normalized.commit import NormalizedOutcome
from pits.normalized.manifest import NormalizedManifest
from pits.sources.trm.contract import BACKFILL_FROM
from pits.sources.trm.normalize import (
    NormalizePermanentError,
    NormalizeTransientError,
    normalize_trm,
)

DAY1 = date(2026, 10, 9)
DAY2 = date(2026, 10, 10)
FIRST_END = date(2026, 10, 9)


def full_rows():
    return [
        raw_row(BACKFILL_FROM, date(2026, 10, 9), "3000.5"),
        raw_row(date(2026, 10, 10), date(2026, 10, 13), "3194.44"),
    ]


def raw_with_full(store=None, batch_id=B1, day=DAY1):
    store = store or MemoryRawStore()
    put_raw_batch(store, batch_id, day, "full", full_rows())
    return store


def run(raw, norm=None):
    norm = norm if norm is not None else MemoryRawStore()
    return normalize_trm(raw, norm, raw_bucket="pits-raw"), norm


class ShuffledStore(MemoryRawStore):
    def list_prefixes(self, prefix):
        return sorted(super().list_prefixes(prefix), reverse=True)


class WriteCountingStore(MemoryRawStore):
    def __init__(self):
        super().__init__()
        self.puts: list[tuple[str, PutOutcome]] = []

    def put_once(self, key, body, content_type):
        outcome = super().put_once(key, body, content_type)
        self.puts.append((key, outcome))
        return outcome


def test_creates_csv_and_manifest_with_expected_content():
    raw = raw_with_full()
    result, norm = run(raw)
    assert result.outcome is NormalizedOutcome.CREATED
    base = (
        "fx_rate/source_system=superfinanciera_trm/inputs_until=2026-10-09/"
        f"fingerprint={result.fingerprint}/"
    )
    assert result.csv_key == base + "fx_rate.csv" and result.manifest_key == base + "manifest.json"
    assert set(norm.objects) == {result.csv_key, result.manifest_key}
    csv = norm.get(result.csv_key).decode().split("\n")
    assert csv[0] == "rate_date,currency_from,currency_to,rate,source_reference"
    assert csv[1].startswith("1991-12-02,USD,COP,3000.5,superfinanciera_trm/")
    assert csv[1].endswith("payload-00000.json#row=0")
    assert [line.split(",")[:4] for line in csv[-5:-1]] == [
        [f"2026-10-{d}", "USD", "COP", "3194.44"] for d in ("10", "11", "12", "13")
    ]
    assert csv[-1] == ""
    manifest = NormalizedManifest.from_json(norm.get(result.manifest_key))
    assert manifest.output.key == result.csv_key
    assert manifest.output.sha256 == sha256_hex(norm.get(result.csv_key))
    assert manifest.output.size_bytes == len(norm.get(result.csv_key))
    assert manifest.row_count == result.rows == len(csv) - 2
    assert manifest.max_range_days == result.max_range_days
    assert (manifest.coverage.from_date, manifest.coverage.to_date) == (
        BACKFILL_FROM,
        date(2026, 10, 13),
    )
    assert manifest.baseline_batch_id == B1 and result.inputs == 1
    assert norm.content_types[result.csv_key] == "text/csv"
    assert norm.content_types[result.manifest_key] == "application/json"


def test_full_plus_incremental_uses_both_and_inputs_until_is_last_extraction():
    raw = raw_with_full()
    put_raw_batch(
        raw,
        B2,
        DAY2,
        "incremental",
        [raw_row(date(2026, 10, 14), date(2026, 10, 14), "3200")],
        from_exclusive=date(2026, 10, 10),
    )
    result, norm = run(raw)
    assert result.inputs == 2 and "inputs_until=2026-10-10" in result.csv_key
    assert norm.get(result.csv_key).decode().rstrip("\n").endswith("#row=0")
    assert "2026-10-14,USD,COP,3200," in norm.get(result.csv_key).decode()
    only_full, _ = run(raw_with_full())
    assert only_full.fingerprint != result.fingerprint


def multi_batch_raw(store):
    """2 partitions; in the second, batch_id order is the opposite of finished_at order."""
    put_raw_batch(store, B1, date(2026, 10, 8), "full", full_rows())
    day = date(2026, 10, 9)
    early = datetime(2026, 10, 9, 13, tzinfo=UTC)
    # B3 sorts after B2 alphabetically but finished earlier -> B2 is applied last and wins.
    put_raw_batch(
        store,
        B3,
        day,
        "incremental",
        [raw_row(date(2026, 10, 14), date(2026, 10, 14), "3200")],
        from_exclusive=date(2026, 10, 10),
        finished_at=early,
    )
    put_raw_batch(
        store,
        B2,
        day,
        "incremental",
        [raw_row(date(2026, 10, 14), date(2026, 10, 14), "3300")],
        from_exclusive=date(2026, 10, 10),
        finished_at=early + timedelta(hours=1),
    )
    return store


class RandomOrderStore(MemoryRawStore):
    def __init__(self, seed):
        super().__init__()
        self.rng = random.Random(seed)

    def list_prefixes(self, prefix):
        found = super().list_prefixes(prefix)
        self.rng.shuffle(found)
        return found


def test_bytes_and_fingerprint_are_independent_of_list_order():
    results = []
    for store in (
        MemoryRawStore(),
        ShuffledStore(),
        RandomOrderStore(1),
        RandomOrderStore(2),
    ):
        result, norm = run(multi_batch_raw(store))
        results.append((result, norm.objects))
    first_result, first_objects = results[0]
    for result, objects in results[1:]:
        assert result.fingerprint == first_result.fingerprint
        assert objects == first_objects
    manifest = NormalizedManifest.from_json(first_objects[first_result.manifest_key])
    assert [i.batch_id for i in manifest.inputs] == [B1, B3, B2]  # commit order, not LIST order
    assert first_result.inputs == 3
    csv = first_objects[first_result.csv_key].decode()
    assert "\n2026-10-14,USD,COP,3300," in csv and ",3200," not in csv  # later wins


def test_two_runs_second_is_already_present_without_new_writes():
    raw = raw_with_full()
    norm = WriteCountingStore()
    first, _ = run(raw, norm)
    assert all(o is PutOutcome.CREATED for _, o in norm.puts)
    snapshot = dict(norm.objects)
    second, _ = run(raw, norm)
    assert first.outcome is NormalizedOutcome.CREATED
    assert second.outcome is NormalizedOutcome.ALREADY_PRESENT
    assert second.fingerprint == first.fingerprint
    assert norm.objects == snapshot
    assert [o for _, o in norm.puts[-2:]] == [PutOutcome.ALREADY_IDENTICAL] * 2


class ManifestFailsOnce(MemoryRawStore):
    def __init__(self):
        super().__init__()
        self.failed = False

    def put_once(self, key, body, content_type):
        if key.endswith("/manifest.json") and not self.failed:
            self.failed = True
            raise RawStoreTransientError("put_object failed: ConnectTimeoutError")
        return super().put_once(key, body, content_type)


def test_crash_between_csv_and_manifest_then_retry_completes():
    raw = raw_with_full()
    norm = ManifestFailsOnce()
    with pytest.raises(NormalizeTransientError):
        normalize_trm(raw, norm, raw_bucket="pits-raw")
    assert [k for k in norm.objects if k.endswith("fx_rate.csv")] and not [
        k for k in norm.objects if k.endswith("manifest.json")
    ]
    result = normalize_trm(raw, norm, raw_bucket="pits-raw")
    assert result.outcome is NormalizedOutcome.CREATED
    assert set(norm.objects) == {result.csv_key, result.manifest_key}


class InterleavingStore(MemoryRawStore):
    """Runner A pauses before its manifest PUT; runner B completes meanwhile."""

    def __init__(self, raw):
        super().__init__()
        self.raw = raw
        self.nested = None
        self.armed = True

    def put_once(self, key, body, content_type):
        if key.endswith("/manifest.json") and self.armed:
            self.armed = False
            self.nested = normalize_trm(self.raw, self, raw_bucket="pits-raw")  # runner B
        return super().put_once(key, body, content_type)


def test_interleaved_runs_both_succeed_with_one_content():
    raw = raw_with_full()
    norm = InterleavingStore(raw)
    a = normalize_trm(raw, norm, raw_bucket="pits-raw")
    b = norm.nested
    assert b.outcome is NormalizedOutcome.CREATED
    assert a.outcome is NormalizedOutcome.ALREADY_PRESENT
    assert a.fingerprint == b.fingerprint and len(norm.objects) == 2


def test_preexisting_different_csv_is_permanent_conflict():
    raw = raw_with_full()
    first, _ = run(raw)
    norm = MemoryRawStore()
    norm.put_once(first.csv_key, b"something else\n", "text/csv")
    with pytest.raises(NormalizePermanentError, match="different content") as err:
        normalize_trm(raw, norm, raw_bucket="pits-raw")
    assert isinstance(err.value.__cause__, RawObjectConflictError)
    assert norm.get(first.csv_key) == b"something else\n"


class FlakyGet(MemoryRawStore):
    def get(self, key):
        raise RawStoreTransientError("get_object failed: ReadTimeoutError")


def test_transient_get_error_is_transient():
    raw = raw_with_full()
    flaky = FlakyGet()
    flaky.objects = raw.objects
    with pytest.raises(NormalizeTransientError):
        normalize_trm(flaky, MemoryRawStore(), raw_bucket="pits-raw")


def test_artifact_is_identical_regardless_of_run_time():
    raw = raw_with_full()
    _, n1 = run(raw)
    _, n2 = run(raw)  # a second process at another moment: no clock is read
    assert n1.objects == n2.objects
    assert b"generated" not in b"".join(n1.objects.values())


def test_normalize_accepts_no_soda_client():
    params = inspect.signature(normalize_trm).parameters
    assert list(params) == ["raw_store", "normalized_store", "raw_bucket", "rules_version"]


def test_over_8_mib_is_permanent_and_writes_nothing():
    raw = MemoryRawStore()
    put_raw_batch(
        raw,
        B1,
        DAY1,
        "full",
        [raw_row(BACKFILL_FROM, date(2250, 1, 1), "3000.5")],
    )
    norm = MemoryRawStore()
    with pytest.raises(NormalizePermanentError, match="byte limit"):
        normalize_trm(raw, norm, raw_bucket="pits-raw")
    assert norm.objects == {}


def test_no_full_batch_is_permanent():
    raw = MemoryRawStore()
    put_raw_batch(
        raw,
        B1,
        DAY1,
        "incremental",
        [raw_row(date(2026, 10, 10), date(2026, 10, 10))],
        from_exclusive=date(2026, 10, 9),
    )
    with pytest.raises(NormalizePermanentError, match="full"):
        normalize_trm(raw, MemoryRawStore(), raw_bucket="pits-raw")


def test_coverage_gap_is_permanent_with_date():
    raw = MemoryRawStore()
    put_raw_batch(
        raw,
        B1,
        DAY1,
        "full",
        [
            raw_row(BACKFILL_FROM, date(2026, 10, 1)),
            raw_row(date(2026, 10, 5), date(2026, 10, 9)),
        ],
    )
    with pytest.raises(NormalizePermanentError, match="2026-10-02"):
        normalize_trm(raw, MemoryRawStore(), raw_bucket="pits-raw")


def test_corrupt_payload_is_permanent_and_writes_nothing():
    raw = raw_with_full()
    key = next(k for k in raw.objects if k.endswith("payload-00000.json"))
    raw.objects[key] = raw.objects[key].replace(b"3000.5", b"9999.5")  # same size, other sha
    norm = MemoryRawStore()
    with pytest.raises(NormalizePermanentError, match="sha256"):
        normalize_trm(raw, norm, raw_bucket="pits-raw")
    assert norm.objects == {}


def test_unit_other_than_cop_is_permanent():
    raw = MemoryRawStore()
    put_raw_batch(raw, B1, DAY1, "full", [raw_row(BACKFILL_FROM, date(2026, 10, 9), unidad="USD")])
    with pytest.raises(NormalizePermanentError, match="unidad"):
        normalize_trm(raw, MemoryRawStore(), raw_bucket="pits-raw")


def test_rules_version_changes_fingerprint_and_key():
    raw = raw_with_full()
    norm = MemoryRawStore()
    a = normalize_trm(raw, norm, raw_bucket="pits-raw")
    b = normalize_trm(raw, norm, raw_bucket="pits-raw", rules_version="trm-v2")
    assert a.fingerprint != b.fingerprint and b.outcome is NormalizedOutcome.CREATED


def test_same_day_batches_pick_latest_finished_as_baseline():
    raw = MemoryRawStore()
    early = datetime(2026, 10, 9, 12, tzinfo=UTC)
    put_raw_batch(raw, B2, DAY1, "full", full_rows(), finished_at=early)
    later = [raw_row(BACKFILL_FROM, date(2026, 10, 9), "1.5")]
    put_raw_batch(raw, B1, DAY1, "full", later, finished_at=early + timedelta(hours=1))
    result, norm = run(raw)
    assert result.baseline_batch_id == B1 and result.inputs == 1
    assert ",1.5," in norm.get(result.csv_key).decode()

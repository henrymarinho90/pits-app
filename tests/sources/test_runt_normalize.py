"""Offline tests for pits.sources.runt.normalize (MemoryRawStore, no SODA)."""

from __future__ import annotations

import dataclasses
import hashlib
import os
import tracemalloc
from datetime import date

import pytest
from runt_support import B1, B2, B3, big_rows, put_runt_batch, raw_row

from pits.ingestion.manifest import Manifest, Watermark
from pits.ingestion.raw_store import MemoryRawStore, RawStoreTransientError
from pits.normalized.commit import NormalizedOutcome
from pits.normalized.fleet_csv import HEADER, MAX_PART_BYTES, MAX_PART_ROWS
from pits.normalized.fleet_manifest import FleetManifest, Publication, artifact_prefix
from pits.sources.runt.contract import WATERMARK_COLUMN
from pits.sources.runt.normalize import (
    NormalizePermanentError,
    NormalizeTransientError,
    normalize_runt,
)

DAY1 = date(2026, 10, 11)
DAY2 = date(2026, 10, 12)


def rows3():
    return [raw_row(2), raw_row(0, cantidad="4"), raw_row(1)]


def run(raw, norm=None):
    norm = norm if norm is not None else MemoryRawStore()
    return list(normalize_runt(raw, norm, raw_bucket="pits-raw")), norm


class FailingStore(MemoryRawStore):
    """Fails (transient) on the nth put_once, like a connection dropping between parts."""

    def __init__(self, fail_on_put: int):
        super().__init__()
        self.fail_on_put = fail_on_put
        self.puts = 0

    def put_once(self, key, body, content_type):
        self.puts += 1
        if self.puts == self.fail_on_put:
            raise RawStoreTransientError("simulated connection drop")
        return super().put_once(key, body, content_type)


class NoPayloadReads(MemoryRawStore):
    """Raw store that fails the test if any payload object is read."""

    def get(self, key):
        assert "payload-" not in key, f"payload read: {key}"
        return super().get(key)


def test_creates_parts_and_manifest_with_expected_content():
    raw = MemoryRawStore()
    put_runt_batch(raw, B1, DAY1, rows3())
    (result,), norm = run(raw)
    assert result.outcome is NormalizedOutcome.CREATED
    assert (result.publication, result.inputs, result.batch_id) == ("2026-10", 1, B1)
    assert (result.rows, result.parts) == (3, 1)
    prefix = (
        "vehicle_fleet_snapshot/source_system=mintransporte_runt_parque/"
        f"publication_month=2026-10/fingerprint={result.fingerprint}/"
    )
    assert result.manifest_key == prefix + "manifest.json"
    assert set(norm.objects) == {prefix + "part-00000.csv", result.manifest_key}
    assert norm.content_types[prefix + "part-00000.csv"] == "text/csv"
    lines = norm.get(prefix + "part-00000.csv").decode().split("\n")
    assert lines[0] == HEADER
    # Ordered by the primary key (municipality), the source_reference points to the raw row.
    assert [line.split(",")[3] for line in lines[1:4]] == ["MUNI000000", "MUNI000001", "MUNI000002"]
    assert lines[1].endswith("payload-00000.json#row=1") and lines[1].split(",")[8] == "4"
    manifest = FleetManifest.from_json(norm.get(result.manifest_key))
    assert manifest.row_count == 3 and manifest.vehicle_count_total == 10
    assert manifest.inputs[0].batch_id == B1 and manifest.input_fingerprint == result.fingerprint


def test_bytes_are_deterministic_across_runs_and_stores():
    raw = MemoryRawStore()
    put_runt_batch(raw, B1, DAY1, big_rows(50), page_size=7)
    (first,), norm1 = run(raw)
    (second,), norm2 = run(raw)
    assert first.fingerprint == second.fingerprint
    assert norm1.objects == norm2.objects
    sha = {k: hashlib.sha256(v).hexdigest() for k, v in norm1.objects.items()}
    assert sha == {k: hashlib.sha256(v).hexdigest() for k, v in norm2.objects.items()}


def test_second_run_on_same_store_is_already_present_without_writes():
    raw = MemoryRawStore()
    put_runt_batch(raw, B1, DAY1, rows3())
    (first,), norm = run(raw)
    before = dict(norm.objects)
    (second,), _ = run(raw, norm)
    assert second.outcome is NormalizedOutcome.ALREADY_PRESENT
    assert (second.fingerprint, second.rows, second.parts) == (first.fingerprint, 3, 1)
    assert norm.objects == before


def test_already_present_does_not_read_any_payload():
    raw = NoPayloadReads()
    put_runt_batch(raw, B1, DAY1, rows3())
    norm = MemoryRawStore()
    with pytest.raises(AssertionError, match="payload read"):  # the first run does read them
        run(raw, norm)
    # Same, with the reads allowed: create it, then forbid payload reads and run again.
    raw2 = MemoryRawStore()
    put_runt_batch(raw2, B1, DAY1, rows3())
    (first,), norm2 = run(raw2)
    guard = NoPayloadReads()
    guard.objects = raw2.objects
    (again,), _ = run(guard, norm2)
    assert again.outcome is NormalizedOutcome.ALREADY_PRESENT
    assert again.fingerprint == first.fingerprint


def test_crash_between_parts_leaves_orphans_and_retry_completes():
    raw = MemoryRawStore()
    put_runt_batch(raw, B1, DAY1, big_rows(45_000), page_size=5000)
    (reference,), clean = run(raw)
    assert reference.parts == 3

    crashing = FailingStore(fail_on_put=2)  # part-00000 written, part-00001 fails
    with pytest.raises(NormalizeTransientError, match="simulated"):
        run(raw, crashing)
    assert sorted(k.rsplit("/", 1)[1] for k in crashing.objects) == ["part-00000.csv"]
    assert not any(k.endswith("manifest.json") for k in crashing.objects)

    crashing.fail_on_put = -1
    (retry,), _ = run(raw, crashing)
    assert retry.outcome is NormalizedOutcome.CREATED
    assert crashing.objects == clean.objects


def test_blank_or_padded_value_is_a_permanent_error_and_writes_nothing():
    for bad in ({"nombre_municipio": ""}, {"nombre_municipio": " CALI"}, {"nombre_servicio": "X "}):
        raw = MemoryRawStore()
        put_runt_batch(raw, B1, DAY1, [raw_row(0), raw_row(1, **bad)])
        norm = MemoryRawStore()
        with pytest.raises(NormalizePermanentError, match="payload-00000.json#row=1"):
            run(raw, norm)
        assert norm.objects == {}


def test_duplicate_primary_key_is_a_permanent_error():
    raw = MemoryRawStore()
    put_runt_batch(raw, B1, DAY1, [raw_row(0), raw_row(1), raw_row(0, cantidad="8")])
    with pytest.raises(NormalizePermanentError, match="duplicate primary key"):
        run(raw)


def test_corrupt_payload_is_a_permanent_error():
    raw = MemoryRawStore()
    put_runt_batch(raw, B1, DAY1, rows3())
    key = next(k for k in raw.objects if k.endswith("payload-00000.json"))
    raw.objects[key] = b"[]"
    with pytest.raises(NormalizePermanentError, match="size mismatch"):
        run(raw)


def test_no_committed_batch_is_a_permanent_error():
    with pytest.raises(NormalizePermanentError, match="No committed raw RUNT batch"):
        run(MemoryRawStore())


def test_two_publications_give_two_artifacts_and_the_old_one_stays_intact():
    raw = MemoryRawStore()
    put_runt_batch(
        raw, B1, DAY1, [raw_row(i, year=2026, month=9) for i in range(3)], year=2026, month=9
    )
    (sept,), norm = run(raw)
    assert sept.publication == "2026-09"
    old = {k: v for k, v in norm.objects.items()}

    put_runt_batch(raw, B2, DAY2, [raw_row(5, year=2026, month=10)], year=2026, month=10)
    results, _ = run(raw, norm)
    assert [(r.publication, r.outcome) for r in results] == [
        ("2026-09", NormalizedOutcome.ALREADY_PRESENT),
        ("2026-10", NormalizedOutcome.CREATED),
    ]
    assert results[0].fingerprint == sept.fingerprint
    assert len({r.manifest_key for r in results}) == 2
    assert all(norm.objects[k] == v for k, v in old.items())  # untouched
    assert len(norm.objects) == len(old) + 2


def test_two_batches_of_the_same_publication_the_last_one_wins():
    raw = MemoryRawStore()
    put_runt_batch(raw, B1, DAY1, [raw_row(0, cantidad="1")])
    put_runt_batch(raw, B2, DAY2, [raw_row(0, cantidad="2"), raw_row(1)])
    (result,), norm = run(raw)
    assert result.batch_id == B2 and result.inputs == 1 and result.rows == 2
    assert FleetManifest.from_json(norm.get(result.manifest_key)).inputs[0].batch_id == B2
    # Order does not depend on the batch id: same day, the later finished_at/batch_id wins.
    raw2 = MemoryRawStore()
    put_runt_batch(raw2, B3, DAY1, [raw_row(0)])
    put_runt_batch(raw2, B1, DAY1, [raw_row(0, cantidad="9")])
    (tie,), _ = run(raw2)
    assert tie.batch_id == B3  # equal date and finished_at: greater batch_id


def test_an_earlier_corrupt_batch_of_the_publication_does_not_matter():
    raw = MemoryRawStore()
    put_runt_batch(raw, B1, DAY1, rows3())
    key = next(k for k in raw.objects if "batch_id=" + B1 in k and k.endswith("payload-00000.json"))
    raw.objects[key] = b"garbage"
    put_runt_batch(raw, B2, DAY2, rows3())
    (result,), _ = run(raw)
    assert result.batch_id == B2


def test_parts_respect_limits_order_and_logical_content():
    raw = MemoryRawStore()
    put_runt_batch(raw, B1, DAY1, big_rows(45_000), page_size=5000)
    (result,), norm = run(raw)
    manifest = FleetManifest.from_json(norm.get(result.manifest_key))
    assert [p.row_count for p in manifest.parts] == [20_000, 20_000, 5_000]
    assert result.parts == 3 and manifest.row_count == 45_000
    header = (HEADER + "\n").encode()
    logical = bytearray(header)
    previous = None
    for entry in manifest.parts:
        body = norm.get(entry.key)
        assert len(body) <= MAX_PART_BYTES and len(body) == entry.size_bytes
        assert hashlib.sha256(body).hexdigest() == entry.sha256
        lines = body.decode().split("\n")
        assert lines[0] == HEADER and lines[-1] == "" and len(lines) - 2 <= MAX_PART_ROWS
        assert len(lines) - 2 == entry.row_count
        logical += body[len(header) :]
        for line in lines[1:-1]:
            # the PK is the first 8 columns; none of the test values contain commas
            key = tuple(line.split(",")[:8])
            sort_key = (int(key[0]), int(key[1]), *key[2:7], int(key[7]))
            assert previous is None or previous < sort_key
            previous = sort_key
    assert manifest.content_sha256 == hashlib.sha256(bytes(logical)).hexdigest()
    assert manifest.content_size_bytes == len(logical)


def test_memory_peak_stays_within_the_linear_share_of_300_mib():
    """D98 budget: 300 MiB for the real batch (192k rows). tracemalloc makes this slow, so the
    default run uses a quarter of it with a quarter of the budget; PITS_MEMORY_TEST_ROWS=192000
    runs the full-size check (measured 76.8 MiB, 65 s on 2026-10-12)."""
    n = int(os.environ.get("PITS_MEMORY_TEST_ROWS", "48000"))
    budget = 300 * 2**20 * n // 192_000
    raw = MemoryRawStore()
    put_runt_batch(raw, B1, DAY1, big_rows(n), page_size=5000)
    norm = MemoryRawStore()
    tracemalloc.start()
    try:
        (result,) = list(normalize_runt(raw, norm, raw_bucket="pits-raw"))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    print(f"rows={n} peak={peak / 2**20:.1f} MiB budget={budget / 2**20:.1f} MiB")
    assert result.rows == n
    assert peak < budget


def _rewrite_raw_manifest(raw, batch_id, day, **changes):
    """Replace a committed raw manifest by a modified (still well-formed) one."""
    key = f"mintransporte_runt_parque/extraction_date={day.isoformat()}/batch_id={batch_id}/"
    key += "manifest.json"
    manifest = Manifest.from_json(raw.objects[key])
    raw.objects[key] = dataclasses.replace(manifest, **changes).to_json()


def _assert_permanent_and_nothing_written(raw, match):
    norm = MemoryRawStore()
    with pytest.raises(NormalizePermanentError, match=match):
        run(raw, norm)
    assert norm.objects == {}


def _seeded():
    raw = MemoryRawStore()
    manifest = put_runt_batch(raw, B1, DAY1, rows3())
    return raw, manifest


def test_batch_with_another_watermark_mode_is_a_permanent_error():
    raw, m = _seeded()
    wm = Watermark(WATERMARK_COLUMN, "incremental", date(2026, 9, 1), date(2026, 10, 1))
    _rewrite_raw_manifest(raw, B1, DAY1, watermark=wm)
    _assert_permanent_and_nothing_written(raw, "not a RUNT full snapshot")


def test_batch_with_another_watermark_column_is_a_permanent_error():
    raw, m = _seeded()
    wm = Watermark("vigenciadesde", "full", None, date(2026, 10, 1))
    _rewrite_raw_manifest(raw, B1, DAY1, watermark=wm)
    _assert_permanent_and_nothing_written(raw, "not a RUNT full snapshot")


def test_batch_with_a_different_schema_is_a_permanent_error():
    raw, m = _seeded()
    _rewrite_raw_manifest(raw, B1, DAY1, schema=m.schema[:-1])
    _assert_permanent_and_nothing_written(raw, "schema other than the RUNT contract")


def test_batch_without_rows_is_a_permanent_error():
    raw, m = _seeded()
    _rewrite_raw_manifest(raw, B1, DAY1, row_count=0, files=())
    _assert_permanent_and_nothing_written(raw, "no rows or no publication")


def test_batch_without_publication_is_a_permanent_error():
    raw, m = _seeded()
    wm = Watermark(WATERMARK_COLUMN, "full", None, None)
    _rewrite_raw_manifest(raw, B1, DAY1, row_count=0, files=(), watermark=wm)
    _assert_permanent_and_nothing_written(raw, "no rows or no publication")


def test_raw_manifest_changing_between_reads_is_a_permanent_error():
    raw, m = _seeded()
    key = (
        f"mintransporte_runt_parque/extraction_date={DAY1.isoformat()}/batch_id={B1}/manifest.json"
    )
    changed = dataclasses.replace(m, source_rows_updated_at=2).to_json()

    class Flapping(MemoryRawStore):
        reads = 0

        def get(self, k):
            if k == key:
                Flapping.reads += 1
                if Flapping.reads > 1:  # list_committed read the original; the replay sees this
                    return changed
            return super().get(k)

    flapping = Flapping()
    flapping.objects = raw.objects
    _assert_permanent_and_nothing_written(flapping, "manifest changed while reading")


def _artifact_manifest():
    raw, _ = _seeded()
    (result,), norm = run(raw)
    return raw, result, FleetManifest.from_json(norm.get(result.manifest_key))


def test_existing_manifest_with_another_fingerprint_is_a_permanent_error():
    raw, result, _ = _artifact_manifest()
    other_raw = MemoryRawStore()
    put_runt_batch(other_raw, B2, DAY2, rows3())
    (other,), other_norm = run(other_raw)
    assert other.fingerprint != result.fingerprint
    # A valid manifest of another artifact sits at this publication's manifest key.
    norm = MemoryRawStore()
    norm.objects[result.manifest_key] = other_norm.get(other.manifest_key)
    before = dict(norm.objects)
    with pytest.raises(NormalizePermanentError, match="content does not match its key"):
        run(raw, norm)
    assert norm.objects == before


def test_existing_manifest_with_another_publication_is_a_permanent_error():
    raw, result, manifest = _artifact_manifest()
    prefix = artifact_prefix("2026-09", manifest.input_fingerprint)
    wrong = dataclasses.replace(
        manifest,
        publication=Publication(2026, 9),
        parts=tuple(
            dataclasses.replace(p, key=prefix + p.key.rsplit("/", 1)[1]) for p in manifest.parts
        ),
    )
    norm = MemoryRawStore()
    norm.objects[result.manifest_key] = wrong.to_json()
    before = dict(norm.objects)
    with pytest.raises(NormalizePermanentError, match="content does not match its key"):
        run(raw, norm)
    assert norm.objects == before

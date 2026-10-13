"""Offline tests for pits.normalized.fleet_reader (MemoryRawStore + the real normalizer)."""

from __future__ import annotations

import hashlib

import pytest
from fleet_artifact_support import (
    RAW_BUCKET,
    add_newer_batch,
    build_raw_and_normalized,
    drop_artifact,
    tricky_rows,
)

from pits.ingestion.raw_store import MemoryRawStore, RawStoreTransientError
from pits.normalized.fleet_csv import HEADER_BYTES
from pits.normalized.fleet_manifest import FleetManifest
from pits.normalized.fleet_reader import iter_parts, read_part, select_artifacts
from pits.normalized.reader import NormalizedReadPermanentError, NormalizedReadTransientError


@pytest.fixture
def env():
    raw, norm, results = build_raw_and_normalized()
    return raw, norm, results


def test_selects_one_artifact_per_publication_ascending(env):
    _, norm, results = env
    selected = select_artifacts(norm, RAW_BUCKET)
    assert [s.publication for s in selected] == ["2026-09", "2026-10"]
    assert [s.manifest.input_fingerprint for s in selected] == [
        results["2026-09"].fingerprint,
        results["2026-10"].fingerprint,
    ]
    assert selected[0].manifest_key == results["2026-09"].manifest_key
    assert selected[0].publication_first_day.isoformat() == "2026-09-01"
    assert selected[0].manifest_sha256 == hashlib.sha256(selected[0].manifest_bytes).hexdigest()


def test_publication_filter(env):
    _, norm, results = env
    (only,) = select_artifacts(norm, RAW_BUCKET, publication="2026-10")
    assert only.manifest.input_fingerprint == results["2026-10"].fingerprint
    with pytest.raises(NormalizedReadPermanentError, match="2026-08"):
        select_artifacts(norm, RAW_BUCKET, publication="2026-08")


def test_latest_artifact_of_a_publication_wins_and_fingerprint_forces_the_old_one(env):
    raw, norm, results = env
    newer = add_newer_batch(raw, norm, (2026, 10), tricky_rows(year=2026, month=10)[:4])
    assert newer.fingerprint != results["2026-10"].fingerprint
    selected = select_artifacts(norm, RAW_BUCKET)
    assert [s.manifest.input_fingerprint for s in selected][1] == newer.fingerprint
    (forced,) = select_artifacts(norm, RAW_BUCKET, fingerprint=results["2026-10"].fingerprint)
    assert forced.manifest.input_fingerprint == results["2026-10"].fingerprint


def test_unknown_fingerprint_is_permanent(env):
    _, norm, _ = env
    with pytest.raises(NormalizedReadPermanentError, match="No committed"):
        select_artifacts(norm, RAW_BUCKET, fingerprint="0" * 64)


def test_invalid_arguments_are_rejected(env):
    _, norm, _ = env
    with pytest.raises(ValueError, match="fingerprint"):
        select_artifacts(norm, RAW_BUCKET, fingerprint="abc")
    with pytest.raises(ValueError, match="publication"):
        select_artifacts(norm, RAW_BUCKET, publication="2026-13")


def test_empty_store_and_wrong_raw_bucket_are_permanent(env):
    _, norm, _ = env
    with pytest.raises(NormalizedReadPermanentError, match="No committed"):
        select_artifacts(MemoryRawStore(), RAW_BUCKET)
    with pytest.raises(NormalizedReadPermanentError, match="No committed"):
        select_artifacts(norm, "other-raw")  # every candidate is ineligible
    with pytest.raises(NormalizedReadPermanentError, match="raw_bucket"):
        select_artifacts(norm, "other-raw", fingerprint=_any_fingerprint(norm))


def _any_fingerprint(norm):
    return select_artifacts(norm, RAW_BUCKET)[0].manifest.input_fingerprint


def test_orphan_parts_without_manifest_are_ignored(env):
    _, norm, results = env
    victim = results["2026-10"]
    del norm.objects[victim.manifest_key]
    assert [s.publication for s in select_artifacts(norm, RAW_BUCKET)] == ["2026-09"]


def test_manifest_that_disagrees_with_its_key_is_permanent(env):
    _, norm, results = env
    # The 2026-10 manifest placed under the 2026-09 publication directory.
    wrong_key = results["2026-09"].manifest_key.replace(
        results["2026-09"].fingerprint, results["2026-10"].fingerprint
    )
    norm.objects[wrong_key] = norm.get(results["2026-10"].manifest_key)
    with pytest.raises(NormalizedReadPermanentError, match="does not match its key"):
        select_artifacts(norm, RAW_BUCKET)


def test_corrupt_manifest_is_permanent(env):
    _, norm, results = env
    norm.objects[results["2026-10"].manifest_key] = b"{not json"
    with pytest.raises(NormalizedReadPermanentError):
        select_artifacts(norm, RAW_BUCKET)


def test_transient_store_error_is_transient(env):
    _, norm, _ = env

    class Down(MemoryRawStore):
        def list_prefixes(self, prefix):
            raise RawStoreTransientError("timeout")

    with pytest.raises(NormalizedReadTransientError):
        select_artifacts(Down(), RAW_BUCKET)


def test_iter_parts_streams_verified_parts_in_order(env):
    _, norm, results = env
    (nine,) = select_artifacts(norm, RAW_BUCKET, publication="2026-09")
    parts = list(iter_parts(norm, nine))
    assert [e.key for e, _ in parts] == [p.key for p in nine.manifest.parts]
    assert all(data.startswith(HEADER_BYTES) for _, data in parts)
    assert sum(e.row_count for e, _ in parts) == results["2026-09"].rows
    manifest = FleetManifest.from_json(nine.manifest_bytes)
    assert manifest == nine.manifest


def test_iter_parts_is_lazy(env):
    _, norm, _ = env
    gets: list[str] = []

    class Spy(MemoryRawStore):
        def get(self, key):
            gets.append(key)
            return super().get(key)

    spy = Spy()
    spy.objects = norm.objects
    (nine,) = select_artifacts(spy, RAW_BUCKET, publication="2026-09")
    gets.clear()
    iterator = iter_parts(spy, nine)
    assert gets == []
    next(iterator)
    assert len(gets) == 1  # one part at a time


@pytest.mark.parametrize("damage", ["flip", "truncate", "missing"])
def test_part_corruption_is_permanent(env, damage):
    _, norm, results = env
    (ten,) = select_artifacts(norm, RAW_BUCKET, publication="2026-10")
    key = ten.manifest.parts[0].key
    data = norm.get(key)
    if damage == "flip":
        norm.objects[key] = data[:-2] + bytes([data[-2] ^ 1]) + data[-1:]
    elif damage == "truncate":
        norm.objects[key] = data[:-1]
    else:
        del norm.objects[key]
    with pytest.raises(NormalizedReadPermanentError):
        list(iter_parts(norm, ten))


def test_part_without_expected_header_is_permanent(env):
    _, norm, _ = env
    (ten,) = select_artifacts(norm, RAW_BUCKET, publication="2026-10")
    entry = ten.manifest.parts[0]
    bad = b"x" * len(HEADER_BYTES) + norm.get(entry.key)[len(HEADER_BYTES) :]
    norm.objects[entry.key] = bad
    # The sha256 is recomputed by the test on purpose: only the header check can catch this.
    forged = type(entry)(entry.key, hashlib.sha256(bad).hexdigest(), len(bad), entry.row_count)
    with pytest.raises(NormalizedReadPermanentError, match="header"):
        read_part(norm, forged)


def test_part_download_failure_is_transient(env):
    _, norm, _ = env
    (ten,) = select_artifacts(norm, RAW_BUCKET, publication="2026-10")

    class Flaky(MemoryRawStore):
        def get(self, key):
            if "part-" in key:
                raise RawStoreTransientError("reset")
            return super().get(key)

    flaky = Flaky()
    flaky.objects = norm.objects
    with pytest.raises(NormalizedReadTransientError):
        list(iter_parts(flaky, ten))


def test_dropping_the_winning_artifact_falls_back_to_the_previous_one(env):
    raw, norm, results = env
    newer = add_newer_batch(raw, norm, (2026, 10), tricky_rows(year=2026, month=10)[:4])
    drop_artifact(norm, newer.fingerprint)
    selected = select_artifacts(norm, RAW_BUCKET, publication="2026-10")
    assert selected[0].manifest.input_fingerprint == results["2026-10"].fingerprint

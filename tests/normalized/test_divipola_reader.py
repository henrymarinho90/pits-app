"""Pure tests for pits.normalized.divipola_reader (selection and verified CSV read)."""

from __future__ import annotations

import pytest
from divipola_artifact_support import (
    RAW_BUCKET,
    add_newer_batch,
    build_raw_and_normalized,
    drop_artifact,
    realistic_rows,
)

from pits.ingestion.raw_store import MemoryRawStore, RawStoreTransientError
from pits.normalized.divipola_csv import HEADER_BYTES
from pits.normalized.divipola_reader import read_csv, select_artifact
from pits.normalized.reader import NormalizedReadPermanentError, NormalizedReadTransientError


def test_selects_the_only_artifact_and_reads_verified_csv():
    _, norm, result = build_raw_and_normalized()
    selected = select_artifact(norm, RAW_BUCKET)
    assert selected.manifest_key == result.manifest_key
    assert selected.manifest.row_count == 5 and selected.rows_updated == result.rows_updated
    assert read_csv(norm, selected).startswith(HEADER_BYTES)


def test_latest_commit_order_wins_and_fingerprint_forces_the_old_one():
    raw, norm, first = build_raw_and_normalized()
    second = add_newer_batch(raw, norm, realistic_rows()[:2])
    assert select_artifact(norm, RAW_BUCKET).manifest.input_fingerprint == second.fingerprint
    forced = select_artifact(norm, RAW_BUCKET, fingerprint=first.fingerprint)
    assert forced.manifest.input_fingerprint == first.fingerprint


def test_orphan_csv_without_manifest_is_ignored():
    raw, norm, first = build_raw_and_normalized()
    second = add_newer_batch(raw, norm, realistic_rows()[:2])
    del norm.objects[second.manifest_key]
    assert select_artifact(norm, RAW_BUCKET).manifest.input_fingerprint == first.fingerprint


def test_no_artifact_is_permanent():
    with pytest.raises(NormalizedReadPermanentError, match="No committed"):
        select_artifact(MemoryRawStore(), RAW_BUCKET)
    _, norm, result = build_raw_and_normalized()
    drop_artifact(norm, result.fingerprint)
    with pytest.raises(NormalizedReadPermanentError):
        select_artifact(norm, RAW_BUCKET)


def test_unknown_fingerprint_is_permanent():
    _, norm, _ = build_raw_and_normalized()
    with pytest.raises(NormalizedReadPermanentError, match="No committed normalized artifact"):
        select_artifact(norm, RAW_BUCKET, fingerprint="0" * 64)


def test_other_raw_bucket_is_not_eligible():
    _, norm, result = build_raw_and_normalized()
    with pytest.raises(NormalizedReadPermanentError, match="No committed"):
        select_artifact(norm, "other-raw")
    with pytest.raises(NormalizedReadPermanentError, match="raw_bucket differs"):
        select_artifact(norm, "other-raw", fingerprint=result.fingerprint)


def test_malformed_fingerprint_is_a_value_error():
    with pytest.raises(ValueError):
        select_artifact(MemoryRawStore(), RAW_BUCKET, fingerprint="xyz")


def test_corrupt_manifest_is_permanent():
    _, norm, result = build_raw_and_normalized()
    norm.objects[result.manifest_key] = b"{}"
    with pytest.raises(NormalizedReadPermanentError):
        select_artifact(norm, RAW_BUCKET)


def test_manifest_under_the_wrong_key_is_permanent():
    _, norm, result = build_raw_and_normalized()
    wrong = result.manifest_key.replace("rows_updated=2025-01-24", "rows_updated=2025-01-25")
    norm.objects[wrong] = norm.objects[result.manifest_key]
    with pytest.raises(NormalizedReadPermanentError, match="does not match its key"):
        select_artifact(norm, RAW_BUCKET, fingerprint=result.fingerprint)


def test_csv_tampering_is_detected():
    _, norm, result = build_raw_and_normalized()
    selected = select_artifact(norm, RAW_BUCKET)
    key = selected.csv_key
    original = norm.objects[key]
    norm.objects[key] = original + b"x"
    with pytest.raises(NormalizedReadPermanentError, match="size"):
        read_csv(norm, selected)
    norm.objects[key] = original.replace(b"MEDELL", b"MEDELX")
    with pytest.raises(NormalizedReadPermanentError, match="sha256"):
        read_csv(norm, selected)
    del norm.objects[key]
    with pytest.raises(NormalizedReadPermanentError):
        read_csv(norm, selected)


def test_transient_store_failure_is_transient():
    _, norm, _ = build_raw_and_normalized()

    def boom(prefix):
        raise RawStoreTransientError("simulated")

    norm.list_prefixes = boom
    with pytest.raises(NormalizedReadTransientError):
        select_artifact(norm, RAW_BUCKET)

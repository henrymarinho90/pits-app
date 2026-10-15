"""Pure tests for pits.normalized.brand_fleet_reader (selection and verified CSV read)."""

from __future__ import annotations

import pytest
from brand_fleet_artifact_support import (
    RAW_BUCKET,
    add_newer_batch,
    boyaca_rows,
    build_raw_and_normalized,
    drop_artifact,
)
from brand_fleet_support import BOYACA, RISARALDA

from pits.ingestion.raw_store import RawStoreTransientError
from pits.normalized.brand_fleet_csv import HEADER_BYTES
from pits.normalized.brand_fleet_reader import read_csv, select_artifact
from pits.normalized.reader import NormalizedReadPermanentError, NormalizedReadTransientError


def test_selects_each_source_and_reads_verified_csv():
    _, norm, results = build_raw_and_normalized()
    for source in (BOYACA, RISARALDA):
        selected = select_artifact(norm, RAW_BUCKET, source)
        result = results[source.key]
        assert selected.manifest_key == result.manifest_key
        assert selected.manifest.source_system == source.source_system
        assert selected.manifest.row_count == result.rows
        assert read_csv(norm, selected).startswith(HEADER_BYTES)


def test_latest_commit_order_wins_and_fingerprint_forces_the_old_one():
    raw, norm, results = build_raw_and_normalized()
    first = results["boyaca"]
    second = add_newer_batch(raw, norm, BOYACA, boyaca_rows()[:2])
    selected = select_artifact(norm, RAW_BUCKET, BOYACA)
    assert selected.manifest.input_fingerprint == second.fingerprint
    forced = select_artifact(norm, RAW_BUCKET, BOYACA, fingerprint=first.fingerprint)
    assert forced.manifest.input_fingerprint == first.fingerprint
    # the other source is unaffected
    other = select_artifact(norm, RAW_BUCKET, RISARALDA)
    assert other.manifest.input_fingerprint == results["risaralda"].fingerprint


def test_fingerprint_of_another_source_is_not_found():
    _, norm, results = build_raw_and_normalized()
    with pytest.raises(NormalizedReadPermanentError, match="No committed normalized artifact"):
        select_artifact(norm, RAW_BUCKET, BOYACA, fingerprint=results["risaralda"].fingerprint)


def test_orphan_csv_without_manifest_is_ignored():
    raw, norm, results = build_raw_and_normalized()
    second = add_newer_batch(raw, norm, BOYACA, boyaca_rows()[:2])
    del norm.objects[second.manifest_key]
    selected = select_artifact(norm, RAW_BUCKET, BOYACA)
    assert selected.manifest.input_fingerprint == results["boyaca"].fingerprint


def test_without_artifacts_is_permanent():
    _, norm, results = build_raw_and_normalized()
    drop_artifact(norm, results["risaralda"].fingerprint)
    with pytest.raises(NormalizedReadPermanentError, match="No committed normalized"):
        select_artifact(norm, RAW_BUCKET, RISARALDA)


def test_other_raw_bucket_is_not_eligible():
    _, norm, _ = build_raw_and_normalized()
    with pytest.raises(NormalizedReadPermanentError, match="No committed normalized"):
        select_artifact(norm, "another-bucket", BOYACA)


def test_tampered_csv_is_permanent():
    _, norm, _ = build_raw_and_normalized()
    selected = select_artifact(norm, RAW_BUCKET, BOYACA)
    norm.objects[selected.csv_key] = norm.objects[selected.csv_key] + b"x"
    with pytest.raises(NormalizedReadPermanentError, match="size"):
        read_csv(norm, selected)
    same_size = bytearray(norm.objects[selected.csv_key][:-1])
    same_size[-3] ^= 0x01
    norm.objects[selected.csv_key] = bytes(same_size) + b"\n"
    with pytest.raises(NormalizedReadPermanentError):
        read_csv(norm, selected)


def test_transient_store_failure_is_transient():
    _, norm, _ = build_raw_and_normalized()

    def boom(prefix):
        raise RawStoreTransientError("simulated")

    norm.list_prefixes = boom
    with pytest.raises(NormalizedReadTransientError):
        select_artifact(norm, RAW_BUCKET, BOYACA)


def test_bad_fingerprint_argument_is_value_error():
    _, norm, _ = build_raw_and_normalized()
    with pytest.raises(ValueError, match="64 lowercase hex"):
        select_artifact(norm, RAW_BUCKET, BOYACA, fingerprint="xyz")

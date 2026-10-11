"""Contract: TRM normalizer against a live, local S3 endpoint (SODA simulated).

Run with: uv run --env-file .env pytest -m contract -q
Real S3RawStore for both zones (raw and normalized, D74): write-once through the real 412
(D75), CSV first / manifest last, and one object version per key after repeated runs.
"""

from __future__ import annotations

from datetime import date

import pytest
from botocore.client import BaseClient
from s3_helpers import BucketFactory
from soda_fake import contiguous_rows, extract_batch

from pits.ingestion.manifest import sha256_hex
from pits.ingestion.raw_store import RawObjectConflictError, S3RawStore
from pits.normalized.commit import NormalizedOutcome
from pits.normalized.manifest import NormalizedManifest
from pits.sources.trm.normalize import NormalizePermanentError, NormalizeResult, normalize_trm

pytestmark = pytest.mark.contract

B1 = "0b6f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a10"
DAY = date(2026, 10, 10)


def _versioned(s3: BaseClient, make_bucket: BucketFactory) -> str:
    name = make_bucket()
    s3.put_bucket_versioning(Bucket=name, VersioningConfiguration={"Status": "Enabled"})
    return name


@pytest.fixture
def buckets(s3: BaseClient, make_bucket: BucketFactory) -> tuple[str, str]:
    return _versioned(s3, make_bucket), _versioned(s3, make_bucket)


def _versions(s3: BaseClient, bucket: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for page in s3.get_paginator("list_object_versions").paginate(Bucket=bucket):
        for v in page.get("Versions", []):
            counts[v["Key"]] = counts.get(v["Key"], 0) + 1
    return counts


def _setup(s3: BaseClient, buckets: tuple[str, str]) -> tuple[S3RawStore, S3RawStore]:
    raw = S3RawStore(s3, buckets[0])
    norm = S3RawStore(s3, buckets[1])
    extract_batch(raw, contiguous_rows(), batch_id=B1, day=DAY)
    return raw, norm


def _normalize(raw: S3RawStore, norm: S3RawStore, raw_bucket: str) -> NormalizeResult:
    return normalize_trm(raw, norm, raw_bucket=raw_bucket)


def test_two_runs_second_is_already_present_with_one_version_each(
    s3: BaseClient, buckets: tuple[str, str]
) -> None:
    raw, norm = _setup(s3, buckets)
    first = _normalize(raw, norm, buckets[0])
    second = _normalize(raw, norm, buckets[0])

    assert first.outcome is NormalizedOutcome.CREATED
    assert second.outcome is NormalizedOutcome.ALREADY_PRESENT
    assert (first.fingerprint, first.csv_key, first.manifest_key) == (
        second.fingerprint,
        second.csv_key,
        second.manifest_key,
    )
    assert _versions(s3, buckets[1]) == {first.csv_key: 1, first.manifest_key: 1}

    csv = s3.get_object(Bucket=buckets[1], Key=first.csv_key)["Body"].read()
    manifest = NormalizedManifest.from_json(
        s3.get_object(Bucket=buckets[1], Key=first.manifest_key)["Body"].read()
    )
    assert manifest.output.sha256 == sha256_hex(csv) and manifest.output.size_bytes == len(csv)
    assert manifest.row_count == first.rows == 34
    # The raw zone was only read: still the extractor's objects, one version each.
    assert set(_versions(s3, buckets[0]).values()) == {1}


def test_only_csv_present_run_completes_the_manifest(
    s3: BaseClient, make_bucket: BucketFactory, buckets: tuple[str, str]
) -> None:
    raw, norm = _setup(s3, buckets)
    first = _normalize(raw, norm, buckets[0])
    expected_csv = s3.get_object(Bucket=buckets[1], Key=first.csv_key)["Body"].read()
    # Crash between the two writes: a fresh normalized bucket holding only the expected CSV,
    # written through put_once (no deletes).
    fresh_name = _versioned(s3, make_bucket)
    fresh = S3RawStore(s3, fresh_name)
    fresh.put_once(first.csv_key, expected_csv, "text/csv")
    assert _versions(s3, fresh_name) == {first.csv_key: 1}

    retry = _normalize(raw, fresh, buckets[0])
    assert retry.outcome is NormalizedOutcome.CREATED
    assert (retry.fingerprint, retry.csv_key) == (first.fingerprint, first.csv_key)
    assert _versions(s3, fresh_name) == {first.csv_key: 1, first.manifest_key: 1}


def test_different_csv_at_the_key_is_a_conflict_with_real_412(
    s3: BaseClient, buckets: tuple[str, str]
) -> None:
    raw, norm = _setup(s3, buckets)
    first = _normalize(raw, norm, buckets[0])
    original = s3.get_object(Bucket=buckets[1], Key=first.csv_key)["Body"].read()
    # Make the bucket look like a crash happened and the CSV had other content: replace it
    # (delete its only version, then write other bytes) and drop the manifest.
    for key in (first.csv_key, first.manifest_key):
        version = s3.list_object_versions(Bucket=buckets[1], Prefix=key)["Versions"][0]
        s3.delete_object(Bucket=buckets[1], Key=key, VersionId=version["VersionId"])
    norm.put_once(first.csv_key, b"not the expected csv\n", "text/csv")

    with pytest.raises(NormalizePermanentError) as exc_info:
        _normalize(raw, norm, buckets[0])
    assert isinstance(exc_info.value.__cause__, RawObjectConflictError)
    # The foreign object is untouched, still a single version, and no manifest was written.
    assert _versions(s3, buckets[1]) == {first.csv_key: 1}
    body = s3.get_object(Bucket=buckets[1], Key=first.csv_key)["Body"].read()
    assert body == b"not the expected csv\n" and body != original

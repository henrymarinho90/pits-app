"""Contract: RUNT normalizer against a live, local S3 endpoint (no SODA).

Run with: uv run --env-file .env pytest -m contract -q
Real S3RawStore for both zones: write-once through the real 412 (D75), parts first and manifest
last, one object version per key after repeated runs, and an interrupted write completed.
"""

from __future__ import annotations

from datetime import date

import pytest
from botocore.client import BaseClient
from runt_support import B1, B2, big_rows, put_runt_batch, raw_row
from s3_helpers import BucketFactory

from pits.ingestion.raw_store import RawObjectConflictError, S3RawStore
from pits.normalized.commit import NormalizedOutcome
from pits.normalized.fleet_manifest import FleetManifest
from pits.sources.runt.normalize import NormalizePermanentError, normalize_runt

pytestmark = pytest.mark.contract

DAY = date(2026, 10, 12)


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


def _stores(s3: BaseClient, buckets: tuple[str, str]) -> tuple[S3RawStore, S3RawStore]:
    return S3RawStore(s3, buckets[0]), S3RawStore(s3, buckets[1])


def test_two_runs_second_is_already_present_with_one_version_each(
    s3: BaseClient, buckets: tuple[str, str]
) -> None:
    raw, norm = _stores(s3, buckets)
    put_runt_batch(raw, B1, DAY, big_rows(45), page_size=10)
    (first,) = list(normalize_runt(raw, norm, raw_bucket=buckets[0]))
    (second,) = list(normalize_runt(raw, norm, raw_bucket=buckets[0]))

    assert first.outcome is NormalizedOutcome.CREATED
    assert second.outcome is NormalizedOutcome.ALREADY_PRESENT
    assert (first.fingerprint, first.manifest_key) == (second.fingerprint, second.manifest_key)
    manifest = FleetManifest.from_json(
        s3.get_object(Bucket=buckets[1], Key=first.manifest_key)["Body"].read()
    )
    assert manifest.row_count == 45
    assert _versions(s3, buckets[1]) == {
        **{p.key: 1 for p in manifest.parts},
        first.manifest_key: 1,
    }
    assert set(_versions(s3, buckets[0]).values()) == {1}  # raw only read


def test_interrupted_write_is_completed_by_the_retry(
    s3: BaseClient, make_bucket: BucketFactory, buckets: tuple[str, str]
) -> None:
    raw, norm = _stores(s3, buckets)
    put_runt_batch(raw, B1, DAY, big_rows(45_000), page_size=5000)
    (first,) = list(normalize_runt(raw, norm, raw_bucket=buckets[0]))
    manifest = FleetManifest.from_json(
        s3.get_object(Bucket=buckets[1], Key=first.manifest_key)["Body"].read()
    )
    # Crash after the first part: a fresh bucket holding only part-00000 (no deletes).
    fresh_name = _versioned(s3, make_bucket)
    fresh = S3RawStore(s3, fresh_name)
    part0 = manifest.parts[0]
    fresh.put_once(
        part0.key, s3.get_object(Bucket=buckets[1], Key=part0.key)["Body"].read(), "text/csv"
    )

    (retry,) = list(normalize_runt(raw, fresh, raw_bucket=buckets[0]))
    assert retry.outcome is NormalizedOutcome.CREATED and retry.fingerprint == first.fingerprint
    assert _versions(s3, fresh_name) == {
        **{p.key: 1 for p in manifest.parts},
        first.manifest_key: 1,
    }


def test_different_part_at_the_key_is_a_conflict_with_real_412(
    s3: BaseClient, buckets: tuple[str, str]
) -> None:
    raw, norm = _stores(s3, buckets)
    put_runt_batch(raw, B1, DAY, [raw_row(0), raw_row(1)])
    (first,) = list(normalize_runt(raw, norm, raw_bucket=buckets[0]))
    part_key = first.manifest_key.replace("manifest.json", "part-00000.csv")
    for key in (part_key, first.manifest_key):
        version = s3.list_object_versions(Bucket=buckets[1], Prefix=key)["Versions"][0]
        s3.delete_object(Bucket=buckets[1], Key=key, VersionId=version["VersionId"])
    norm.put_once(part_key, b"not the expected part\n", "text/csv")

    with pytest.raises(NormalizePermanentError) as exc_info:
        list(normalize_runt(raw, norm, raw_bucket=buckets[0]))
    assert isinstance(exc_info.value.__cause__, RawObjectConflictError)
    assert _versions(s3, buckets[1]) == {part_key: 1}  # foreign part untouched, no manifest


def test_new_publication_leaves_the_old_artifact_untouched(
    s3: BaseClient, buckets: tuple[str, str]
) -> None:
    raw, norm = _stores(s3, buckets)
    put_runt_batch(raw, B1, DAY, [raw_row(0, year=2026, month=9)], year=2026, month=9)
    (sept,) = list(normalize_runt(raw, norm, raw_bucket=buckets[0]))
    before = _versions(s3, buckets[1])
    put_runt_batch(raw, B2, DAY, [raw_row(0)], year=2026, month=10)
    results = list(normalize_runt(raw, norm, raw_bucket=buckets[0]))
    assert [r.publication for r in results] == ["2026-09", "2026-10"]
    assert results[0].outcome is NormalizedOutcome.ALREADY_PRESENT
    assert results[0].fingerprint == sept.fingerprint
    after = _versions(s3, buckets[1])
    assert all(after[k] == v for k, v in before.items()) and len(after) == len(before) + 2

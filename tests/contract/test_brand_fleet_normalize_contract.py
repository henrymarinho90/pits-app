"""Contract: regional brand fleet normalizer against a live, local S3 endpoint (no SODA).

Run with: uv run --env-file .env pytest -m contract -q -k brand_fleet
Real S3RawStore for both zones: write-once through the real 412 (D75), CSV first and manifest
last, one object version per key after repeated runs, an interrupted write completed, and the
two sources kept apart.
"""

from __future__ import annotations

from datetime import date

import pytest
from botocore.client import BaseClient
from brand_fleet_artifact_support import boyaca_rows, risaralda_rows
from brand_fleet_support import B1, BOYACA, RISARALDA, put_brand_batch
from s3_helpers import BucketFactory

from pits.ingestion.raw_store import RawObjectConflictError, S3RawStore
from pits.normalized.brand_fleet_manifest import BrandFleetManifest
from pits.normalized.commit import NormalizedOutcome
from pits.sources.brand_fleet.normalize import NormalizePermanentError, normalize_brand_fleet

pytestmark = pytest.mark.contract

DAY = date(2026, 10, 14)


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


def _manifest(s3: BaseClient, bucket: str, key: str) -> BrandFleetManifest:
    return BrandFleetManifest.from_json(s3.get_object(Bucket=bucket, Key=key)["Body"].read())


def test_two_runs_second_is_already_present_with_one_version_each(
    s3: BaseClient, buckets: tuple[str, str]
) -> None:
    raw, norm = S3RawStore(s3, buckets[0]), S3RawStore(s3, buckets[1])
    put_brand_batch(raw, BOYACA, B1, DAY, boyaca_rows(), page_size=4)
    first = normalize_brand_fleet(raw, norm, BOYACA, raw_bucket=buckets[0])
    second = normalize_brand_fleet(raw, norm, BOYACA, raw_bucket=buckets[0])

    assert first.outcome is NormalizedOutcome.CREATED
    assert second.outcome is NormalizedOutcome.ALREADY_PRESENT
    assert (first.fingerprint, first.manifest_key) == (second.fingerprint, second.manifest_key)
    manifest = _manifest(s3, buckets[1], first.manifest_key)
    assert (manifest.row_count, manifest.vehicle_total) == (4, 6)
    assert _versions(s3, buckets[1]) == {manifest.output.key: 1, first.manifest_key: 1}
    assert set(_versions(s3, buckets[0]).values()) == {1}  # raw only read


def test_the_two_sources_have_separate_artifacts(s3: BaseClient, buckets: tuple[str, str]) -> None:
    raw, norm = S3RawStore(s3, buckets[0]), S3RawStore(s3, buckets[1])
    put_brand_batch(raw, BOYACA, B1, DAY, boyaca_rows())
    put_brand_batch(raw, RISARALDA, B1, DAY, risaralda_rows())
    a = normalize_brand_fleet(raw, norm, BOYACA, raw_bucket=buckets[0])
    b = normalize_brand_fleet(raw, norm, RISARALDA, raw_bucket=buckets[0])
    assert a.manifest_key != b.manifest_key
    assert f"source_system={BOYACA.source_system}/" in a.manifest_key
    assert f"source_system={RISARALDA.source_system}/" in b.manifest_key
    assert len(_versions(s3, buckets[1])) == 4  # csv + manifest per source


def test_interrupted_write_is_completed_by_the_retry(
    s3: BaseClient, make_bucket: BucketFactory, buckets: tuple[str, str]
) -> None:
    raw, norm = S3RawStore(s3, buckets[0]), S3RawStore(s3, buckets[1])
    put_brand_batch(raw, RISARALDA, B1, DAY, risaralda_rows())
    first = normalize_brand_fleet(raw, norm, RISARALDA, raw_bucket=buckets[0])
    manifest = _manifest(s3, buckets[1], first.manifest_key)
    # Crash after the CSV: a fresh bucket holding only the CSV (no deletes).
    fresh_name = _versioned(s3, make_bucket)
    fresh = S3RawStore(s3, fresh_name)
    fresh.put_once(
        manifest.output.key,
        s3.get_object(Bucket=buckets[1], Key=manifest.output.key)["Body"].read(),
        "text/csv",
    )
    retry = normalize_brand_fleet(raw, fresh, RISARALDA, raw_bucket=buckets[0])
    assert retry.outcome is NormalizedOutcome.CREATED and retry.fingerprint == first.fingerprint
    assert _versions(s3, fresh_name) == {manifest.output.key: 1, first.manifest_key: 1}


def test_different_csv_at_the_key_is_a_conflict_with_real_412(
    s3: BaseClient, buckets: tuple[str, str]
) -> None:
    raw, norm = S3RawStore(s3, buckets[0]), S3RawStore(s3, buckets[1])
    put_brand_batch(raw, BOYACA, B1, DAY, boyaca_rows())
    first = normalize_brand_fleet(raw, norm, BOYACA, raw_bucket=buckets[0])
    csv_key = first.manifest_key.replace("manifest.json", "brand_count.csv")
    for key in (csv_key, first.manifest_key):
        version = s3.list_object_versions(Bucket=buckets[1], Prefix=key)["Versions"][0]
        s3.delete_object(Bucket=buckets[1], Key=key, VersionId=version["VersionId"])
    norm.put_once(csv_key, b"not the expected csv\n", "text/csv")

    with pytest.raises(NormalizePermanentError) as exc_info:
        normalize_brand_fleet(raw, norm, BOYACA, raw_bucket=buckets[0])
    assert isinstance(exc_info.value.__cause__, RawObjectConflictError)
    assert _versions(s3, buckets[1]) == {csv_key: 1}  # foreign CSV untouched, no manifest

"""Contract: conditional put_object(IfNoneMatch="*") on a live, local S3 endpoint.

Run with: uv run --env-file .env pytest -m contract -q
Decides D62 (write-once per batch_id enforced with IfNoneMatch="*").
Observed on SeaweedFS 4.48: supported; 2nd put -> 412 PreconditionFailed.
"""

from __future__ import annotations

import pytest
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from s3_helpers import BucketFactory

from pits.ingestion.raw_store import PutOutcome, RawObjectConflictError, S3RawStore

pytestmark = pytest.mark.contract

KEY = "src/extraction_date=2026-01-01/batch_id=abc/part-0.json"


def _versions(s3: BaseClient, bucket: str) -> tuple[int, int]:
    resp = s3.list_object_versions(Bucket=bucket)
    return len(resp.get("Versions", [])), len(resp.get("DeleteMarkers", []))


def _put(s3: BaseClient, bucket: str, body: bytes) -> None:
    s3.put_object(Bucket=bucket, Key=KEY, Body=body, IfNoneMatch="*")


@pytest.fixture(params=[False, True], ids=["unversioned", "versioned"])
def prepared(request: pytest.FixtureRequest, s3: BaseClient, make_bucket: BucketFactory) -> str:
    name = make_bucket()
    if request.param:
        s3.put_bucket_versioning(Bucket=name, VersioningConfiguration={"Status": "Enabled"})
    return name


def test_second_conditional_put_is_rejected_and_content_intact(
    s3: BaseClient, prepared: str
) -> None:
    _put(s3, prepared, b"first")
    with pytest.raises(ClientError) as exc_info:
        _put(s3, prepared, b"second")
    error = exc_info.value.response
    assert error["Error"]["Code"] == "PreconditionFailed"
    assert error["ResponseMetadata"]["HTTPStatusCode"] == 412
    assert s3.get_object(Bucket=prepared, Key=KEY)["Body"].read() == b"first"
    assert _versions(s3, prepared) == (1, 0)


def test_conditional_put_after_delete_marker_succeeds(
    s3: BaseClient, make_bucket: BucketFactory
) -> None:
    # Observed on SeaweedFS 4.48: after a delete without VersionId (delete marker) the key
    # counts as absent, so IfNoneMatch="*" succeeds and creates a new version (same as AWS).
    # Consequence: write-once must also forbid deletes in the raw bucket (policy, not S3).
    bucket = make_bucket()
    s3.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
    _put(s3, bucket, b"first")
    s3.delete_object(Bucket=bucket, Key=KEY)
    assert _versions(s3, bucket) == (1, 1)
    _put(s3, bucket, b"third")
    assert s3.get_object(Bucket=bucket, Key=KEY)["Body"].read() == b"third"
    assert _versions(s3, bucket) == (2, 1)
    # The pre-delete version is still readable by VersionId.
    versions = s3.list_object_versions(Bucket=bucket)["Versions"]
    old = next(v for v in versions if not v["IsLatest"])
    assert s3.get_object(Bucket=bucket, Key=KEY, VersionId=old["VersionId"])["Body"].read() == (
        b"first"
    )


def test_s3_raw_store_identical_put_is_already_identical_with_one_version(
    s3: BaseClient, prepared: str
) -> None:
    store = S3RawStore(s3, prepared)
    assert store.put_once(KEY, b"same", "application/json") is PutOutcome.CREATED
    assert store.put_once(KEY, b"same", "application/json") is PutOutcome.ALREADY_IDENTICAL
    assert _versions(s3, prepared) == (1, 0)


def test_s3_raw_store_different_put_is_conflict_with_one_version(
    s3: BaseClient, prepared: str
) -> None:
    store = S3RawStore(s3, prepared)
    store.put_once(KEY, b"first", "application/json")
    with pytest.raises(RawObjectConflictError, match="batch_id=abc"):
        store.put_once(KEY, b"second", "application/json")
    assert s3.get_object(Bucket=prepared, Key=KEY)["Body"].read() == b"first"
    assert _versions(s3, prepared) == (1, 0)

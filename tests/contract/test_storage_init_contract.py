"""Contract tests for ensure_raw_bucket against a live, local S3 endpoint (SeaweedFS).

Run with: uv run --env-file .env pytest -m contract -q
Buckets are named pits-contract-<uuid8>, which load_storage_settings rejects on purpose,
so ensure_raw_bucket is called directly here.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from s3_helpers import BucketFactory, purge_bucket

from pits.storage.raw_bucket import RawBucketError, ensure_raw_bucket

pytestmark = pytest.mark.contract


@pytest.fixture
def new_name(s3: BaseClient) -> Iterator[str]:
    """A fresh bucket name that does not exist yet; purged at teardown if created."""
    name = f"pits-contract-{uuid.uuid4().hex[:8]}"
    yield name
    try:
        s3.head_bucket(Bucket=name)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in {"404", "NoSuchBucket", "NotFound"}:
            return
        raise
    purge_bucket(s3, name)


def _status(s3: BaseClient, bucket: str) -> str | None:
    return s3.get_bucket_versioning(Bucket=bucket).get("Status")


def test_missing_bucket_is_created_and_second_run_is_noop(s3: BaseClient, new_name: str) -> None:
    first = ensure_raw_bucket(s3, new_name)
    assert (first.created, first.versioning_changed) == (True, True)
    assert _status(s3, new_name) == "Enabled"

    second = ensure_raw_bucket(s3, new_name)
    assert (second.created, second.versioning_changed) == (False, False)
    assert _status(s3, new_name) == "Enabled"


def test_existing_bucket_without_versioning_gets_it_enabled(
    s3: BaseClient, make_bucket: BucketFactory
) -> None:
    name = make_bucket()
    assert _status(s3, name) is None
    result = ensure_raw_bucket(s3, name)
    assert (result.created, result.versioning_changed) == (False, True)
    assert _status(s3, name) == "Enabled"


def test_suspended_versioning_is_an_error_and_left_untouched(
    s3: BaseClient, make_bucket: BucketFactory
) -> None:
    name = make_bucket()
    s3.put_bucket_versioning(Bucket=name, VersioningConfiguration={"Status": "Enabled"})
    s3.put_bucket_versioning(Bucket=name, VersioningConfiguration={"Status": "Suspended"})
    with pytest.raises(RawBucketError, match="Suspended"):
        ensure_raw_bucket(s3, name)
    assert _status(s3, name) == "Suspended"


def test_create_bucket_on_own_existing_bucket_reports_already_owned(
    s3: BaseClient, make_bucket: BucketFactory
) -> None:
    # Observed on SeaweedFS 4.48: 409 BucketAlreadyOwnedByYou (AWS us-east-1 returns 200).
    # raw_bucket._create_bucket treats this code as a lost race and continues.
    name = make_bucket()
    with pytest.raises(ClientError) as exc_info:
        s3.create_bucket(Bucket=name)
    assert exc_info.value.response["Error"]["Code"] == "BucketAlreadyOwnedByYou"
    assert exc_info.value.response["ResponseMetadata"]["HTTPStatusCode"] == 409


class _HeadMissesOnce:
    """Client proxy whose first head_bucket says 404, simulating a lost create race."""

    def __init__(self, client: BaseClient) -> None:
        self._client = client
        self._missed = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    def head_bucket(self, **kwargs: Any) -> Any:
        if not self._missed:
            self._missed = True
            raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadBucket")
        return self._client.head_bucket(**kwargs)


def test_lost_create_race_is_handled_against_real_endpoint(
    s3: BaseClient, make_bucket: BucketFactory
) -> None:
    name = make_bucket()  # another process "won" the creation
    result = ensure_raw_bucket(_HeadMissesOnce(s3), name)  # type: ignore[arg-type]
    assert (result.created, result.versioning_changed) == (False, True)
    assert _status(s3, name) == "Enabled"

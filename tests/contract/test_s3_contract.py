from collections.abc import Callable

import pytest
from botocore.client import BaseClient
from botocore.exceptions import ClientError

pytestmark = pytest.mark.contract

# SeaweedFS 4.48 returns InvalidAccessKeyId (HTTP 403) for an unknown access key.
AUTH_ERROR_CODES = {"InvalidAccessKeyId", "SignatureDoesNotMatch", "AccessDenied"}


def test_create_bucket(s3: BaseClient, bucket: str) -> None:
    s3.head_bucket(Bucket=bucket)
    names = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    assert bucket in names


def test_rejects_invalid_credentials(make_client: Callable[[str, str], BaseClient]) -> None:
    bad = make_client("fake-access-key", "fake-secret-key-0123456789")
    with pytest.raises(ClientError) as exc_info:
        bad.list_buckets()
    assert exc_info.value.response["Error"]["Code"] in AUTH_ERROR_CODES

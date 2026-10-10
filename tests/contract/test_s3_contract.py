import hashlib
import unicodedata
from collections.abc import Callable

import pytest
from botocore.client import BaseClient
from botocore.exceptions import ClientError

pytestmark = pytest.mark.contract

# SeaweedFS 4.48 returns InvalidAccessKeyId (HTTP 403) for an unknown access key.
AUTH_ERROR_CODES = {"InvalidAccessKeyId", "SignatureDoesNotMatch", "AccessDenied"}


def list_keys(s3: BaseClient, bucket: str, **kwargs: object) -> list[str]:
    paginator = s3.get_paginator("list_objects_v2")
    return [
        obj["Key"]
        for page in paginator.paginate(Bucket=bucket, **kwargs)
        for obj in page.get("Contents", [])
    ]


def test_create_bucket(s3: BaseClient, bucket: str) -> None:
    s3.head_bucket(Bucket=bucket)
    names = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    assert bucket in names


def test_rejects_invalid_credentials(make_client: Callable[[str, str], BaseClient]) -> None:
    bad = make_client("fake-access-key", "fake-secret-key-0123456789")
    with pytest.raises(ClientError) as exc_info:
        bad.list_buckets()
    assert exc_info.value.response["Error"]["Code"] in AUTH_ERROR_CODES


def test_put_get_list(s3: BaseClient, bucket: str) -> None:
    objects = {f"data/part-{i}.json": f'{{"i": {i}}}'.encode() for i in range(5)}
    objects["other/readme.txt"] = b"hello"
    for key, body in objects.items():
        s3.put_object(Bucket=bucket, Key=key, Body=body)
    for key, body in objects.items():
        assert s3.get_object(Bucket=bucket, Key=key)["Body"].read() == body

    # Pagination: MaxKeys=2 over 5 objects under the prefix -> 3 pages (2+2+1).
    pages = list(
        s3.get_paginator("list_objects_v2").paginate(
            Bucket=bucket, Prefix="data/", PaginationConfig={"PageSize": 2}
        )
    )
    assert [len(p["Contents"]) for p in pages] == [2, 2, 1]
    assert sorted(o["Key"] for p in pages for o in p["Contents"]) == sorted(
        k for k in objects if k.startswith("data/")
    )
    assert list_keys(s3, bucket, Prefix="other/") == ["other/readme.txt"]
    assert len(list_keys(s3, bucket)) == 6


def test_zero_byte_object(s3: BaseClient, bucket: str) -> None:
    s3.put_object(Bucket=bucket, Key="empty", Body=b"")
    resp = s3.get_object(Bucket=bucket, Key="empty")
    assert resp["ContentLength"] == 0
    assert resp["Body"].read() == b""


def test_unicode_and_space_keys(s3: BaseClient, bucket: str) -> None:
    keys = [
        "raw/trm/extraction_date=2026-10-10/año fiscal/Bogotá D.C./señal.json",
        "raw/a  b+c/double  space + plus.json",
        "raw/pct/100%25 done%2Fx %.json",
    ]
    for key in keys:
        assert unicodedata.is_normalized("NFC", key)
        s3.put_object(Bucket=bucket, Key=key, Body=key.encode())
    for key in keys:
        assert s3.head_object(Bucket=bucket, Key=key)["ContentLength"] == len(key.encode())
        assert s3.get_object(Bucket=bucket, Key=key)["Body"].read() == key.encode()
    assert sorted(list_keys(s3, bucket)) == sorted(keys)


def test_nfd_key_does_not_collide_with_nfc(s3: BaseClient, bucket: str) -> None:
    """S3 keys are bytes: NFC and NFD forms of the same text must be distinct objects."""
    nfc = "raw/Bogotá/señal.json"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    s3.put_object(Bucket=bucket, Key=nfc, Body=b"nfc")
    s3.put_object(Bucket=bucket, Key=nfd, Body=b"nfd")
    assert s3.get_object(Bucket=bucket, Key=nfc)["Body"].read() == b"nfc"
    assert s3.get_object(Bucket=bucket, Key=nfd)["Body"].read() == b"nfd"
    assert sorted(list_keys(s3, bucket)) == sorted([nfc, nfd])


def test_reupload_same_key_is_idempotent(s3: BaseClient, bucket: str) -> None:
    key, body = "raw/dataset/part-0.json", b'{"a": 1}'
    s3.put_object(Bucket=bucket, Key=key, Body=b'{"a": 0}')  # older content, overwritten below
    responses = [s3.put_object(Bucket=bucket, Key=key, Body=body) for _ in range(2)]
    etags = [r["ETag"] for r in responses]
    expected_etag = '"' + hashlib.md5(body).hexdigest() + '"'  # noqa: S324 (S3 ETag, not security)
    assert etags[0] == etags[1] == expected_etag
    assert s3.get_object(Bucket=bucket, Key=key)["Body"].read() == body
    assert s3.head_object(Bucket=bucket, Key=key)["ETag"] == expected_etag
    assert list_keys(s3, bucket) == [key]
    listing = s3.list_object_versions(Bucket=bucket)
    assert len(listing.get("Versions", [])) == 1  # 3 PUTs, 1 version
    assert not listing.get("DeleteMarkers")
    # Finding (SeaweedFS 4.48, bucket without versioning): put_object returns no VersionId,
    # while list_object_versions reports the single version as VersionId "null".
    assert {r.get("VersionId") for r in responses} == {None}
    assert [v["VersionId"] for v in listing["Versions"]] == ["null"]

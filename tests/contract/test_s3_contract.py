import datetime as dt
import hashlib
import math
import os
import tracemalloc
import unicodedata
from collections.abc import Callable

import pytest
from boto3.s3.transfer import TransferConfig
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from s3_helpers import MIB, BucketFactory, RandomStream, S3Settings

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
    # md5 here reproduces the S3 ETag of a single-part PUT; it is not used for security.
    expected_etag = '"' + hashlib.md5(body).hexdigest() + '"'
    assert etags[0] == etags[1] == expected_etag
    got = s3.get_object(Bucket=bucket, Key=key)
    assert got["Body"].read() == body
    assert got.get("VersionId") is None
    assert s3.head_object(Bucket=bucket, Key=key)["ETag"] == expected_etag
    assert list_keys(s3, bucket) == [key]
    listing = s3.list_object_versions(Bucket=bucket)
    assert len(listing.get("Versions", [])) == 1  # 3 PUTs, 1 version
    assert not listing.get("DeleteMarkers")
    # Finding (SeaweedFS 4.48, bucket without versioning): put_object returns no VersionId,
    # while list_object_versions reports the single version as VersionId "null".
    assert {r.get("VersionId") for r in responses} == {None}
    assert [v["VersionId"] for v in listing["Versions"]] == ["null"]


def test_large_object_streaming(s3: BaseClient, bucket: str, s3_settings: S3Settings) -> None:
    """Multipart upload and streamed download of an incompressible object, bounded memory."""
    size = s3_settings.large_mb * MIB
    part = 8 * MIB
    key = "raw/large/blob.bin"
    source = RandomStream(size)
    # max_in_memory_upload_chunks bounds the s3transfer read-ahead queue (default 10 chunks =
    # 80 MiB of 8 MiB parts); lowering it pins a known client memory budget.
    config = TransferConfig(
        multipart_threshold=part,
        multipart_chunksize=part,
        max_concurrency=2,
    )
    config.max_in_memory_upload_chunks = 4  # attribute of s3transfer's config, not a ctor arg

    tracemalloc.start()
    try:
        s3.upload_fileobj(source, bucket, key, Config=config)
        head = s3.head_object(Bucket=bucket, Key=key)
        digest = hashlib.sha256()
        body = s3.get_object(Bucket=bucket, Key=key)["Body"]
        for chunk in body.iter_chunks(MIB):
            digest.update(chunk)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    print(f"large object: size={size} peak_tracemalloc={peak} ETag={head['ETag']}")
    assert head["ContentLength"] == size
    assert digest.hexdigest() == source.sha256.hexdigest()
    parts = math.ceil(size / part)
    assert head["ETag"].strip('"').endswith(f"-{parts}")
    # Budget tied to the config: queued chunks + in-flight workers + 16 MiB of slack.
    budget = (config.max_in_memory_upload_chunks + config.max_concurrency) * part + 16 * MIB
    assert peak < budget
    assert peak < size  # documentary: implied by the budget above (budget < size for >= 100 MiB)


def test_manual_multipart_etag_format(s3: BaseClient, bucket: str) -> None:
    """Complete ETag is md5(concat(md5(part))) + "-N" (S3 format), same in head_object."""
    key = "raw/multipart/manual.bin"
    parts = [os.urandom(5 * MIB), os.urandom(5 * MIB), os.urandom(1000)]
    upload = s3.create_multipart_upload(Bucket=bucket, Key=key)
    done_parts = []
    for number, data in enumerate(parts, start=1):
        resp = s3.upload_part(
            Bucket=bucket, Key=key, UploadId=upload["UploadId"], PartNumber=number, Body=data
        )
        done_parts.append({"PartNumber": number, "ETag": resp["ETag"]})
    done = s3.complete_multipart_upload(
        Bucket=bucket,
        Key=key,
        UploadId=upload["UploadId"],
        MultipartUpload={"Parts": done_parts},
    )
    # md5 reproduces the S3 multipart ETag format; it is not used for security.
    inner = hashlib.md5(b"".join(hashlib.md5(p).digest() for p in parts)).hexdigest()
    expected = f'"{inner}-3"'
    assert done["ETag"] == expected
    assert s3.head_object(Bucket=bucket, Key=key)["ETag"] == expected
    assert s3.get_object(Bucket=bucket, Key=key)["Body"].read() == b"".join(parts)


def error_of(exc: ClientError) -> tuple[str, int]:
    return exc.response["Error"]["Code"], exc.response["ResponseMetadata"]["HTTPStatusCode"]


def test_versioning(s3: BaseClient, bucket: str) -> None:
    s3.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
    key = "raw/versioned.json"
    v1 = s3.put_object(Bucket=bucket, Key=key, Body=b"old")["VersionId"]
    v2 = s3.put_object(Bucket=bucket, Key=key, Body=b"new")["VersionId"]
    assert v1 != v2
    listing = s3.list_object_versions(Bucket=bucket, Prefix=key)
    assert {v["VersionId"] for v in listing["Versions"]} == {v1, v2}
    assert s3.get_object(Bucket=bucket, Key=key, VersionId=v1)["Body"].read() == b"old"
    assert s3.get_object(Bucket=bucket, Key=key)["Body"].read() == b"new"

    marker = s3.delete_object(Bucket=bucket, Key=key)
    assert marker["DeleteMarker"] is True
    listing = s3.list_object_versions(Bucket=bucket, Prefix=key)
    assert [m["VersionId"] for m in listing["DeleteMarkers"]] == [marker["VersionId"]]
    assert s3.get_object(Bucket=bucket, Key=key, VersionId=v1)["Body"].read() == b"old"
    with pytest.raises(ClientError) as exc_info:
        s3.get_object(Bucket=bucket, Key=key)
    assert error_of(exc_info.value) == ("NoSuchKey", 404)


def test_object_lock_enabled_bucket(s3: BaseClient, make_bucket: BucketFactory) -> None:
    bucket = make_bucket(object_lock=True)
    config = s3.get_object_lock_configuration(Bucket=bucket)["ObjectLockConfiguration"]
    assert config["ObjectLockEnabled"] == "Enabled"
    assert s3.get_bucket_versioning(Bucket=bucket)["Status"] == "Enabled"


def test_object_lock_compliance(s3: BaseClient, make_bucket: BucketFactory) -> None:
    bucket = make_bucket(object_lock=True)
    make_bucket.keep(bucket)  # COMPLIANCE objects cannot be purged until retention expires
    key = "raw/compliance.bin"
    until = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=2)
    put = s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=b"v1",
        ObjectLockMode="COMPLIANCE",
        ObjectLockRetainUntilDate=until,
    )
    v1 = put["VersionId"]
    server_date = dt.datetime.strptime(
        put["ResponseMetadata"]["HTTPHeaders"]["date"], "%a, %d %b %Y %H:%M:%S GMT"
    ).replace(tzinfo=dt.UTC)
    skew = abs((dt.datetime.now(dt.UTC) - server_date).total_seconds())
    print(f"compliance: bucket={bucket} v1={v1} server_date={server_date} clock_skew_s={skew:.1f}")
    assert skew < 30, "client/server clock skew makes retention checks unreliable"

    def denied(call: Callable[..., object], **kwargs: object) -> tuple[str, int]:
        with pytest.raises(ClientError) as exc_info:
            call(**kwargs)
        return error_of(exc_info.value)

    results = {
        "delete_version": denied(s3.delete_object, Bucket=bucket, Key=key, VersionId=v1),
        "delete_version_bypass": denied(
            s3.delete_object,
            Bucket=bucket,
            Key=key,
            VersionId=v1,
            BypassGovernanceRetention=True,
        ),
        "shorten_retention": denied(
            s3.put_object_retention,
            Bucket=bucket,
            Key=key,
            VersionId=v1,
            Retention={"Mode": "COMPLIANCE", "RetainUntilDate": until - dt.timedelta(minutes=1)},
        ),
    }
    print(f"compliance denials: {results}")
    assert all(code == "AccessDenied" and status == 403 for code, status in results.values())

    initial = s3.get_object_retention(Bucket=bucket, Key=key, VersionId=v1)["Retention"]
    assert initial["Mode"] == "COMPLIANCE"
    # The server stores whole seconds.
    assert abs((initial["RetainUntilDate"] - until).total_seconds()) < 1

    # Positive control: COMPLIANCE retention can be extended (never shortened).
    longer = until + dt.timedelta(minutes=1)
    s3.put_object_retention(
        Bucket=bucket,
        Key=key,
        VersionId=v1,
        Retention={"Mode": "COMPLIANCE", "RetainUntilDate": longer},
    )
    retention = s3.get_object_retention(Bucket=bucket, Key=key, VersionId=v1)["Retention"]
    assert retention["Mode"] == "COMPLIANCE"
    assert abs((retention["RetainUntilDate"] - longer).total_seconds()) < 1

    # Overwrite succeeds: it creates v2 and leaves the locked v1 untouched.
    v2 = s3.put_object(Bucket=bucket, Key=key, Body=b"v2")["VersionId"]
    assert v2 != v1
    old = s3.get_object(Bucket=bucket, Key=key, VersionId=v1)["Body"].read()
    assert hashlib.sha256(old).digest() == hashlib.sha256(b"v1").digest()
    assert s3.get_object_retention(Bucket=bucket, Key=key, VersionId=v1)["Retention"] == retention

    # Control: v2 has no retention, and the same identity CAN delete it, so the 403 on v1
    # is caused by the retention and not by missing permissions.
    with pytest.raises(ClientError) as v2_exc:
        s3.get_object_retention(Bucket=bucket, Key=key, VersionId=v2)
    print(f"retention of an unlocked version: {error_of(v2_exc.value)}")
    assert error_of(v2_exc.value) == ("ObjectLockConfigurationNotFoundError", 404)
    assert s3.delete_object(Bucket=bucket, Key=key, VersionId=v2)["VersionId"] == v2

    # Delete without VersionId only adds a delete marker; v1 stays readable.
    assert s3.delete_object(Bucket=bucket, Key=key)["DeleteMarker"] is True
    assert s3.get_object(Bucket=bucket, Key=key, VersionId=v1)["Body"].read() == b"v1"


def test_object_lock_governance_bypass(s3: BaseClient, make_bucket: BucketFactory) -> None:
    bucket = make_bucket(object_lock=True)
    make_bucket.keep(bucket)  # GOVERNANCE retention also blocks the purge until it expires
    key = "raw/governance.bin"
    until = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=2)
    v1 = s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=b"g",
        ObjectLockMode="GOVERNANCE",
        ObjectLockRetainUntilDate=until,
    )["VersionId"]
    with pytest.raises(ClientError) as exc_info:
        s3.delete_object(Bucket=bucket, Key=key, VersionId=v1)
    assert error_of(exc_info.value) == ("AccessDenied", 403)
    deleted = s3.delete_object(Bucket=bucket, Key=key, VersionId=v1, BypassGovernanceRetention=True)
    assert deleted["VersionId"] == v1


def test_object_lock_legal_hold(s3: BaseClient, make_bucket: BucketFactory) -> None:
    bucket = make_bucket(object_lock=True)
    key = "raw/hold.bin"
    v1 = s3.put_object(Bucket=bucket, Key=key, Body=b"h")["VersionId"]
    s3.put_object_legal_hold(Bucket=bucket, Key=key, VersionId=v1, LegalHold={"Status": "ON"})
    assert s3.get_object_legal_hold(Bucket=bucket, Key=key, VersionId=v1)["LegalHold"] == {
        "Status": "ON"
    }
    with pytest.raises(ClientError) as exc_info:
        s3.delete_object(Bucket=bucket, Key=key, VersionId=v1)
    assert error_of(exc_info.value) == ("AccessDenied", 403)
    s3.put_object_legal_hold(Bucket=bucket, Key=key, VersionId=v1, LegalHold={"Status": "OFF"})
    assert s3.delete_object(Bucket=bucket, Key=key, VersionId=v1)["VersionId"] == v1

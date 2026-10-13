"""Contract tests of the S3 identities and the write-once bucket policy (D104(a)(b)(c), D104(e)).

Run (after `docker compose up` with the S3 config and `pits storage init`):
    uv run --env-file ../pits-app/.env pytest -m contract -q -k policy       # contract bucket
    uv run --env-file ../pits-app/.env pytest -m contract -q -k identity     # real buckets

Two groups:
- `policy`: a throwaway pits-contract-<uuid> bucket and the admin identity only (the writer and
  reader identities are scoped to the platform buckets, so they cannot touch contract buckets;
  that scoping is itself asserted). The fixture removes the policy and purges at teardown.
- `identity`: the real raw/normalized buckets with the writer/reader identities. Non-destructive
  when the identities are correct: reads, lists, multipart create+abort (permission probe that
  leaves no object)
  and denied deletes on keys that do not exist (`_pits_probe/<uuid>`).

A denied DeleteObjects answers HTTP 200 with a per-key `Errors` entry (S3 semantics), so those
checks read the response body instead of an HTTP status.

PITS_S3_WRITER_* / PITS_S3_READER_* come from the environment; without them the tests skip.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator

import boto3
import pytest
from botocore import UNSIGNED
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError
from s3_helpers import BucketFactory, S3Settings

from pits.storage.raw_bucket import ensure_versioned_bucket, ensure_write_once_policy

pytestmark = pytest.mark.contract

ClientFactory = Callable[[str, str], BaseClient]


def _code(exc: ClientError) -> str:
    return str(exc.response["Error"]["Code"])


def _http(exc: ClientError) -> int:
    return int(exc.response["ResponseMetadata"]["HTTPStatusCode"])


def _assert_denied(call: Callable[[], object], hint: str = "") -> None:
    try:
        call()
    except ClientError as exc:
        assert _http(exc) == 403, exc.response["Error"]
        assert _code(exc) == "AccessDenied"
        return
    pytest.fail(f"call was NOT denied (expected 403 AccessDenied){hint}", pytrace=False)


def _assert_multi_delete_denied(client: BaseClient, bucket: str, key: str) -> None:
    response = client.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": key}]})
    assert not response.get("Deleted"), response
    assert [e["Code"] for e in response.get("Errors", [])] == ["AccessDenied"], response


def _identity(env_prefix: str, make_client: ClientFactory) -> BaseClient:
    key = os.environ.get(f"{env_prefix}_ACCESS_KEY_ID", "").strip()
    secret = os.environ.get(f"{env_prefix}_SECRET_ACCESS_KEY", "").strip()
    if not key or not secret:
        pytest.skip(
            f"{env_prefix}_ACCESS_KEY_ID/_SECRET_ACCESS_KEY not set (see .env.example, D104)"
        )
    return make_client(key, secret)


@pytest.fixture
def writer(make_client: ClientFactory) -> BaseClient:
    return _identity("PITS_S3_WRITER", make_client)


@pytest.fixture
def reader(make_client: ClientFactory) -> BaseClient:
    return _identity("PITS_S3_READER", make_client)


@pytest.fixture
def anonymous(s3_settings: S3Settings) -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=s3_settings.endpoint_url,
        region_name=s3_settings.region,
        config=Config(
            signature_version=UNSIGNED, s3={"addressing_style": "path"}, retries={"max_attempts": 1}
        ),
    )


# --- policy: throwaway contract bucket, admin identity ---------------------------------------


@pytest.fixture
def policy_bucket(s3: BaseClient, make_bucket: BucketFactory) -> Iterator[str]:
    """Contract bucket with versioning Enabled and the write-once policy applied."""
    name = make_bucket()
    ensure_versioned_bucket(s3, name)
    ensure_write_once_policy(s3, name)  # same order as `pits storage init`
    yield name
    # Teardown: the policy denies deletes to admin too; lift it so make_bucket can purge.
    s3.delete_bucket_policy(Bucket=name)


def test_policy_apply_is_idempotent_and_survives_second_init_order(
    s3: BaseClient, policy_bucket: str
) -> None:
    # SeaweedFS stores/normalizes the document: the re-read must still count as equivalent.
    assert ensure_write_once_policy(s3, policy_bucket) is False
    # Second `init`: versioning is Enabled, so PutBucketVersioning (now denied) is not called.
    assert ensure_versioned_bucket(s3, policy_bucket).versioning_changed is False


def test_policy_denies_admin_delete_and_versioning_change(
    s3: BaseClient, policy_bucket: str
) -> None:
    put = s3.put_object(Bucket=policy_bucket, Key="data/a.csv", Body=b"a")
    _assert_denied(lambda: s3.delete_object(Bucket=policy_bucket, Key="data/a.csv"))
    _assert_denied(
        lambda: s3.delete_object(Bucket=policy_bucket, Key="data/a.csv", VersionId=put["VersionId"])
    )
    _assert_denied(
        lambda: s3.put_bucket_versioning(
            Bucket=policy_bucket, VersioningConfiguration={"Status": "Suspended"}
        )
    )
    # Nothing was removed and writes still work (write-once, not read-only).
    assert s3.get_object(Bucket=policy_bucket, Key="data/a.csv")["Body"].read() == b"a"
    s3.put_object(Bucket=policy_bucket, Key="data/b.csv", Body=b"b")
    assert s3.get_bucket_versioning(Bucket=policy_bucket)["Status"] == "Enabled"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "SeaweedFS 4.48: the admin identity bypasses the bucket policy in DeleteObjects "
        "(multi-delete). Known limitation of D104(c); strict xfail: remove the mark when fixed."
    ),
)
def test_policy_denies_admin_multi_delete(s3: BaseClient, policy_bucket: str) -> None:
    s3.put_object(Bucket=policy_bucket, Key="data/m.csv", Body=b"m")
    _assert_multi_delete_denied(s3, policy_bucket, "data/m.csv")


def test_policy_denies_anonymous(anonymous: BaseClient, policy_bucket: str) -> None:
    _assert_denied(lambda: anonymous.list_objects_v2(Bucket=policy_bucket))
    _assert_denied(lambda: anonymous.get_object(Bucket=policy_bucket, Key="x"))
    _assert_denied(lambda: anonymous.put_object(Bucket=policy_bucket, Key="x", Body=b"x"))
    _assert_denied(lambda: anonymous.delete_object(Bucket=policy_bucket, Key="x"))


def test_policy_writer_and_reader_are_scoped_to_platform_buckets(
    writer: BaseClient, reader: BaseClient, s3: BaseClient, policy_bucket: str
) -> None:
    s3.put_object(Bucket=policy_bucket, Key="x", Body=b"x")
    for client in (writer, reader):
        _assert_denied(lambda c=client: c.list_objects_v2(Bucket=policy_bucket))
        _assert_denied(lambda c=client: c.get_object(Bucket=policy_bucket, Key="x"))
        _assert_denied(lambda c=client: c.put_object(Bucket=policy_bucket, Key="y", Body=b"y"))
        _assert_denied(lambda c=client: c.put_bucket_policy(Bucket=policy_bucket, Policy="{}"))
        _assert_denied(
            lambda c=client: c.create_bucket(Bucket=f"pits-contract-{uuid.uuid4().hex[:8]}")
        )


# --- identity: real buckets, writer and reader (non-destructive) -----------------------------


def _platform_buckets() -> list[str]:
    raw = os.environ.get("S3_RAW_BUCKET", "").strip()
    if not raw:
        pytest.skip("S3_RAW_BUCKET not set")
    return [raw, os.environ.get("S3_NORMALIZED_BUCKET", "").strip() or "pits-normalized"]


@pytest.fixture(params=["raw", "normalized"])
def platform_bucket(request: pytest.FixtureRequest, s3: BaseClient) -> str:
    bucket = _platform_buckets()[0 if request.param == "raw" else 1]
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as exc:
        pytest.fail(f"bucket '{bucket}' unavailable ({_code(exc)}): run `pits storage init` first")
    return bucket


def _missing_key() -> str:
    return f"_pits_probe/{uuid.uuid4()}"


def _assert_can_read(client: BaseClient, bucket: str) -> None:
    client.head_bucket(Bucket=bucket)
    assert client.get_bucket_versioning(Bucket=bucket).get("Status") == "Enabled"
    client.list_objects_v2(Bucket=bucket, MaxKeys=1)
    with pytest.raises(ClientError) as info:  # allowed to read: a missing key is 404, not 403
        client.get_object(Bucket=bucket, Key=_missing_key())
    assert _http(info.value) == 404


def _assert_no_destructive_access(client: BaseClient, bucket: str, admin: BaseClient) -> None:
    key = _missing_key()
    # Deleting a non-existent key succeeds (204) without the policy: 403 proves the deny.
    _assert_denied(lambda: client.delete_object(Bucket=bucket, Key=key))
    _assert_denied(lambda: client.delete_object(Bucket=bucket, Key=key, VersionId=uuid.uuid4().hex))
    _assert_multi_delete_denied(client, bucket, key)
    _assert_denied(
        lambda: client.put_bucket_versioning(
            Bucket=bucket, VersioningConfiguration={"Status": "Enabled"}
        )
    )
    _assert_denied(lambda: client.put_bucket_policy(Bucket=bucket, Policy="{}"))
    _assert_denied(
        lambda: client.delete_bucket_policy(Bucket=bucket),
        hint=f": the policy of '{bucket}' may be gone, re-run `pits storage init`",
    )
    _assert_denied(lambda: client.delete_bucket(Bucket=bucket))
    other = f"pits-other-{uuid.uuid4().hex[:8]}"
    try:
        _assert_denied(lambda: client.create_bucket(Bucket=other))
    finally:
        try:  # only reached with a bucket when the identity is wrongly allowed to create it
            admin.delete_bucket(Bucket=other)
        except ClientError:
            pass  # expected: the bucket does not exist because the creation was denied


def test_identity_writer_reads_lists_and_writes_but_cannot_destroy(
    writer: BaseClient, platform_bucket: str, s3: BaseClient
) -> None:
    _assert_can_read(writer, platform_bucket)
    # Write permission probe that leaves no object behind (the policy forbids cleaning up).
    upload = writer.create_multipart_upload(Bucket=platform_bucket, Key=_missing_key())
    writer.abort_multipart_upload(
        Bucket=platform_bucket, Key=upload["Key"], UploadId=upload["UploadId"]
    )
    _assert_no_destructive_access(writer, platform_bucket, s3)


def test_identity_reader_reads_and_lists_but_cannot_write_or_destroy(
    reader: BaseClient, platform_bucket: str, s3: BaseClient
) -> None:
    _assert_can_read(reader, platform_bucket)
    _assert_denied(
        lambda: reader.create_multipart_upload(Bucket=platform_bucket, Key=_missing_key())
    )
    _assert_denied(
        lambda: reader.put_object(
            Bucket=platform_bucket, Key=_missing_key(), Body=b"x", IfNoneMatch="*"
        )
    )
    _assert_no_destructive_access(reader, platform_bucket, s3)


def test_identity_admin_is_blocked_by_the_policy_on_real_buckets(
    s3: BaseClient, platform_bucket: str
) -> None:
    key = _missing_key()
    _assert_denied(lambda: s3.delete_object(Bucket=platform_bucket, Key=key))
    _assert_denied(
        lambda: s3.delete_object(Bucket=platform_bucket, Key=key, VersionId=uuid.uuid4().hex)
    )
    _assert_denied(
        lambda: s3.put_bucket_versioning(
            Bucket=platform_bucket, VersioningConfiguration={"Status": "Suspended"}
        )
    )


def test_identity_anonymous_is_denied_on_real_buckets(
    anonymous: BaseClient, platform_bucket: str
) -> None:
    _assert_denied(lambda: anonymous.list_objects_v2(Bucket=platform_bucket))
    _assert_denied(lambda: anonymous.delete_object(Bucket=platform_bucket, Key=_missing_key()))


def test_identity_orphans_matrix_reader_lists_both_buckets(reader: BaseClient) -> None:
    for bucket in _platform_buckets():
        reader.list_objects_v2(Bucket=bucket, Prefix="", MaxKeys=1)
        reader.list_object_versions(Bucket=bucket, MaxKeys=1)

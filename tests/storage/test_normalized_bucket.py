"""Offline tests for the normalized bucket (D74): settings, ensure_versioned_bucket, verify."""

from __future__ import annotations

import pytest
from botocore.client import BaseClient
from botocore.stub import Stubber

from pits.storage.client import build_s3_client
from pits.storage.raw_bucket import (
    EnsureResult,
    RawBucketError,
    ensure_raw_bucket,
    ensure_versioned_bucket,
    verify_versioned_bucket,
)
from pits.storage.settings import StorageConfigError, StorageSettings, load_storage_settings

ENV = {
    "S3_ENDPOINT_URL": "http://127.0.0.1:8333",
    "S3_ACCESS_KEY_ID": "AKIDEXAMPLE0001",
    "S3_SECRET_ACCESS_KEY": "super-secret-value-123",
    "S3_RAW_BUCKET": "pits-raw",
}
BUCKET = "pits-normalized"
PARAMS = {"Bucket": BUCKET}
ENABLE = {"Bucket": BUCKET, "VersioningConfiguration": {"Status": "Enabled"}}


# --- settings -----------------------------------------------------------------------------


def test_normalized_bucket_defaults_to_pits_normalized() -> None:
    assert load_storage_settings(ENV, identity="admin").normalized_bucket == "pits-normalized"


def test_blank_normalized_bucket_uses_default() -> None:
    assert load_storage_settings(
        {**ENV, "S3_NORMALIZED_BUCKET": "  "}, identity="admin"
    ).normalized_bucket == ("pits-normalized")


def test_normalized_bucket_from_env() -> None:
    assert load_storage_settings(
        {**ENV, "S3_NORMALIZED_BUCKET": "my-norm"}, identity="admin"
    ).normalized_bucket == ("my-norm")


@pytest.mark.parametrize("bucket", ["ab", "Pits-Norm", "pits_norm", "xn--pits", "192.168.0.1"])
def test_invalid_normalized_bucket_names_the_variable(bucket: str) -> None:
    with pytest.raises(StorageConfigError, match="S3_NORMALIZED_BUCKET") as exc:
        load_storage_settings({**ENV, "S3_NORMALIZED_BUCKET": bucket}, identity="admin")
    assert ENV["S3_SECRET_ACCESS_KEY"] not in str(exc.value)


def test_normalized_bucket_with_contract_prefix_rejected() -> None:
    with pytest.raises(StorageConfigError, match=r"S3_NORMALIZED_BUCKET.*pits-contract-"):
        load_storage_settings(
            {**ENV, "S3_NORMALIZED_BUCKET": "pits-contract-abcd1234"}, identity="admin"
        )


def test_normalized_bucket_must_differ_from_raw() -> None:
    with pytest.raises(StorageConfigError, match="must differ"):
        load_storage_settings({**ENV, "S3_NORMALIZED_BUCKET": "pits-raw"}, identity="admin")
    with pytest.raises(StorageConfigError, match="must differ"):
        load_storage_settings({**ENV, "S3_RAW_BUCKET": "pits-normalized"}, identity="admin")


def test_raw_bucket_error_message_unchanged() -> None:
    with pytest.raises(StorageConfigError, match="S3_RAW_BUCKET is not a valid S3 bucket name"):
        load_storage_settings({**ENV, "S3_RAW_BUCKET": "Pits-Raw"}, identity="admin")


# --- ensure_versioned_bucket / verify ----------------------------------------------------


@pytest.fixture
def client() -> BaseClient:
    return build_s3_client(
        StorageSettings(
            "http://127.0.0.1:9", "AKIDEXAMPLE0001", "secret-for-tests-only", "us-east-1", "x"
        )
    )


def _versioning(stubber: Stubber, status: str | None) -> None:
    stubber.add_response("get_bucket_versioning", {"Status": status} if status else {}, PARAMS)


def test_ensure_versioned_bucket_creates_and_enables(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        stubber.add_client_error("head_bucket", "404", http_status_code=404, expected_params=PARAMS)
        stubber.add_response("create_bucket", {}, PARAMS)
        _versioning(stubber, None)
        stubber.add_response("put_bucket_versioning", {}, ENABLE)
        _versioning(stubber, "Enabled")
        result = ensure_versioned_bucket(client, BUCKET)
        stubber.assert_no_pending_responses()
    assert result == EnsureResult(BUCKET, created=True, versioning_changed=True)


def test_ensure_versioned_bucket_suspended_is_error(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        stubber.add_response("head_bucket", {}, PARAMS)
        _versioning(stubber, "Suspended")
        with pytest.raises(RawBucketError, match="Suspended"):
            ensure_versioned_bucket(client, BUCKET)
        stubber.assert_no_pending_responses()


def test_ensure_raw_bucket_wrapper_behaves_the_same(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        stubber.add_response("head_bucket", {}, PARAMS)
        _versioning(stubber, "Enabled")
        result = ensure_raw_bucket(client, BUCKET)
        stubber.assert_no_pending_responses()
    assert result == EnsureResult(BUCKET, created=False, versioning_changed=False)


def test_verify_passes_when_enabled_and_makes_no_writes(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        stubber.add_response("head_bucket", {}, PARAMS)
        _versioning(stubber, "Enabled")
        verify_versioned_bucket(client, BUCKET)
        stubber.assert_no_pending_responses()


def test_verify_missing_bucket_is_error_and_never_creates(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        stubber.add_client_error("head_bucket", "404", http_status_code=404, expected_params=PARAMS)
        with pytest.raises(RawBucketError, match="does not exist"):
            verify_versioned_bucket(client, BUCKET)
        stubber.assert_no_pending_responses()


@pytest.mark.parametrize(("status", "word"), [(None, "not enabled"), ("Suspended", "Suspended")])
def test_verify_without_enabled_versioning_is_error(
    client: BaseClient, status: str | None, word: str
) -> None:
    with Stubber(client) as stubber:
        stubber.add_response("head_bucket", {}, PARAMS)
        _versioning(stubber, status)
        with pytest.raises(RawBucketError, match=word):
            verify_versioned_bucket(client, BUCKET)
        stubber.assert_no_pending_responses()


def test_verify_access_denied_is_error(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        stubber.add_client_error("head_bucket", "403", http_status_code=403, expected_params=PARAMS)
        with pytest.raises(RawBucketError, match="Access denied"):
            verify_versioned_bucket(client, BUCKET)
        stubber.assert_no_pending_responses()

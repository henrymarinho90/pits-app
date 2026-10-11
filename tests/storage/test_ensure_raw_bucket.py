"""Offline tests for pits.storage.raw_bucket and client, using botocore Stubber."""

import pytest
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from botocore.stub import Stubber

from pits.storage.client import build_s3_client
from pits.storage.raw_bucket import EnsureResult, RawBucketError, ensure_raw_bucket
from pits.storage.settings import StorageSettings

BUCKET = "pits-raw"
BUCKET_PARAMS = {"Bucket": BUCKET}
ENABLE = {"Bucket": BUCKET, "VersioningConfiguration": {"Status": "Enabled"}}


def _settings(region: str = "us-east-1") -> StorageSettings:
    return StorageSettings(
        endpoint_url="http://127.0.0.1:9",
        access_key_id="AKIDEXAMPLE0001",
        secret_access_key="secret-for-tests-only",
        region=region,
        raw_bucket=BUCKET,
    )


@pytest.fixture
def client() -> BaseClient:
    return build_s3_client(_settings())


def _head_error(stubber: Stubber, code: str, status: int) -> None:
    stubber.add_client_error(
        "head_bucket",
        service_error_code=code,
        http_status_code=status,
        expected_params=BUCKET_PARAMS,
    )


def _versioning(stubber: Stubber, status: str | None) -> None:
    response = {"Status": status} if status else {}
    stubber.add_response("get_bucket_versioning", response, BUCKET_PARAMS)


def _create_path(stubber: Stubber, code: str = "404") -> None:
    """head missing -> create -> versioning off -> enable -> verify."""
    _head_error(stubber, code, 404)
    stubber.add_response("create_bucket", {}, BUCKET_PARAMS)
    _versioning(stubber, None)
    stubber.add_response("put_bucket_versioning", {}, ENABLE)
    _versioning(stubber, "Enabled")


@pytest.mark.parametrize("code", ["404", "NoSuchBucket", "NotFound"])
def test_creates_bucket_and_enables_versioning(client: BaseClient, code: str) -> None:
    with Stubber(client) as stubber:
        _create_path(stubber, code)
        result = ensure_raw_bucket(client, BUCKET)
        stubber.assert_no_pending_responses()
    assert result == EnsureResult(BUCKET, created=True, versioning_changed=True)


def test_existing_enabled_bucket_makes_no_write_calls(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        stubber.add_response("head_bucket", {}, BUCKET_PARAMS)
        _versioning(stubber, "Enabled")
        result = ensure_raw_bucket(client, BUCKET)
        stubber.assert_no_pending_responses()
    assert result == EnsureResult(BUCKET, created=False, versioning_changed=False)


def test_existing_bucket_without_versioning_enables_it(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        stubber.add_response("head_bucket", {}, BUCKET_PARAMS)
        _versioning(stubber, None)
        stubber.add_response("put_bucket_versioning", {}, ENABLE)
        _versioning(stubber, "Enabled")
        result = ensure_raw_bucket(client, BUCKET)
        stubber.assert_no_pending_responses()
    assert result == EnsureResult(BUCKET, created=False, versioning_changed=True)


def test_second_run_is_a_no_op(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        _create_path(stubber)
        first = ensure_raw_bucket(client, BUCKET)
        stubber.add_response("head_bucket", {}, BUCKET_PARAMS)
        _versioning(stubber, "Enabled")
        second = ensure_raw_bucket(client, BUCKET)
        stubber.assert_no_pending_responses()
    assert (first.created, first.versioning_changed) == (True, True)
    assert (second.created, second.versioning_changed) == (False, False)


def test_suspended_versioning_is_an_error(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        stubber.add_response("head_bucket", {}, BUCKET_PARAMS)
        _versioning(stubber, "Suspended")
        with pytest.raises(RawBucketError, match="Suspended"):
            ensure_raw_bucket(client, BUCKET)
        stubber.assert_no_pending_responses()


@pytest.mark.parametrize("code", ["403", "Forbidden", "AccessDenied"])
def test_head_denied_is_an_error(client: BaseClient, code: str) -> None:
    with Stubber(client) as stubber:
        _head_error(stubber, code, 403)
        with pytest.raises(RawBucketError, match="Access denied"):
            ensure_raw_bucket(client, BUCKET)
        stubber.assert_no_pending_responses()


def test_head_unexpected_error_is_an_error(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        _head_error(stubber, "500", 500)
        with pytest.raises(RawBucketError, match="head_bucket"):
            ensure_raw_bucket(client, BUCKET)
        stubber.assert_no_pending_responses()


def test_create_race_already_owned_by_you_continues(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        _head_error(stubber, "404", 404)
        stubber.add_client_error(
            "create_bucket",
            service_error_code="BucketAlreadyOwnedByYou",
            http_status_code=409,
            expected_params=BUCKET_PARAMS,
        )
        _versioning(stubber, "Enabled")
        result = ensure_raw_bucket(client, BUCKET)
        stubber.assert_no_pending_responses()
    assert result == EnsureResult(BUCKET, created=False, versioning_changed=False)


def test_create_other_error_is_an_error(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        _head_error(stubber, "404", 404)
        stubber.add_client_error(
            "create_bucket",
            service_error_code="BucketAlreadyExists",
            http_status_code=409,
            expected_params=BUCKET_PARAMS,
        )
        with pytest.raises(RawBucketError, match="create_bucket"):
            ensure_raw_bucket(client, BUCKET)
        stubber.assert_no_pending_responses()


def test_put_versioning_error_is_an_error(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        stubber.add_response("head_bucket", {}, BUCKET_PARAMS)
        _versioning(stubber, None)
        stubber.add_client_error(
            "put_bucket_versioning",
            service_error_code="AccessDenied",
            http_status_code=403,
            expected_params=ENABLE,
        )
        with pytest.raises(RawBucketError, match="put_bucket_versioning"):
            ensure_raw_bucket(client, BUCKET)
        stubber.assert_no_pending_responses()


def test_get_versioning_error_is_an_error(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        stubber.add_response("head_bucket", {}, BUCKET_PARAMS)
        stubber.add_client_error(
            "get_bucket_versioning",
            service_error_code="InternalError",
            http_status_code=500,
            expected_params=BUCKET_PARAMS,
        )
        with pytest.raises(RawBucketError, match="get_bucket_versioning"):
            ensure_raw_bucket(client, BUCKET)
        stubber.assert_no_pending_responses()


def test_final_verification_failure_is_an_error(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        stubber.add_response("head_bucket", {}, BUCKET_PARAMS)
        _versioning(stubber, None)
        stubber.add_response("put_bucket_versioning", {}, ENABLE)
        _versioning(stubber, None)
        with pytest.raises(RawBucketError, match="after enabling"):
            ensure_raw_bucket(client, BUCKET)
        stubber.assert_no_pending_responses()


def test_non_default_region_sends_location_constraint() -> None:
    regional = build_s3_client(_settings(region="us-west-2"))
    with Stubber(regional) as stubber:
        _head_error(stubber, "404", 404)
        stubber.add_response(
            "create_bucket",
            {},
            {"Bucket": BUCKET, "CreateBucketConfiguration": {"LocationConstraint": "us-west-2"}},
        )
        _versioning(stubber, "Enabled")
        result = ensure_raw_bucket(regional, BUCKET)
        stubber.assert_no_pending_responses()
    assert result.created is True


def test_client_config_path_style_timeouts_and_retries(client: BaseClient) -> None:
    config = client.meta.config
    assert config.s3["addressing_style"] == "path"
    assert (config.connect_timeout, config.read_timeout) == (5, 60)
    # botocore reports max_attempts=3 (retries) as total_max_attempts=4 (first call + 3 retries).
    assert config.retries["mode"] == "standard"
    assert config.retries["total_max_attempts"] == 4


def test_botocore_accepts_conditional_put_if_none_match(client: BaseClient) -> None:
    params = {"Bucket": BUCKET, "Key": "k", "Body": b"x", "IfNoneMatch": "*"}
    with Stubber(client) as stubber:
        stubber.add_response("put_object", {}, params)
        client.put_object(**params)
        stubber.add_client_error(
            "put_object", service_error_code="PreconditionFailed", http_status_code=412
        )
        with pytest.raises(ClientError) as exc:
            client.put_object(**params)
        stubber.assert_no_pending_responses()
    assert exc.value.response["Error"]["Code"] == "PreconditionFailed"

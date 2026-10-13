"""Offline tests for the write-once bucket policy (D104(c)) using botocore Stubber."""

import json

import pytest
from botocore.client import BaseClient
from botocore.stub import Stubber

from pits.storage.client import build_s3_client
from pits.storage.raw_bucket import (
    DENY_DELETE_SID,
    DENY_VERSIONING_SID,
    RawBucketError,
    RawBucketTransientError,
    ensure_versioned_bucket,
    ensure_write_once_policy,
    write_once_policy,
)
from pits.storage.settings import StorageSettings

BUCKET = "pits-raw"
PARAMS = {"Bucket": BUCKET}


@pytest.fixture
def client() -> BaseClient:
    return build_s3_client(
        StorageSettings(
            "http://127.0.0.1:9", "AKIDEXAMPLE0001", "secret-for-tests-only", "", BUCKET
        )
    )


def _doc(bucket: str = BUCKET) -> str:
    return json.dumps(write_once_policy(bucket), sort_keys=True, separators=(",", ":"))


def _no_policy(stubber: Stubber) -> None:
    stubber.add_client_error(
        "get_bucket_policy", "NoSuchBucketPolicy", http_status_code=404, expected_params=PARAMS
    )


def test_policy_shape_denies_delete_and_versioning_for_everyone() -> None:
    policy = write_once_policy(BUCKET)
    by_sid = {st["Sid"]: st for st in policy["Statement"]}
    assert set(by_sid) == {DENY_DELETE_SID, DENY_VERSIONING_SID}
    assert all(st["Effect"] == "Deny" and st["Principal"] == "*" for st in by_sid.values())
    delete = by_sid[DENY_DELETE_SID]
    assert delete["Action"] == ["s3:DeleteObject", "s3:DeleteObjectVersion"]
    assert delete["Resource"] == f"arn:aws:s3:::{BUCKET}/*"
    versioning = by_sid[DENY_VERSIONING_SID]
    assert versioning["Action"] == "s3:PutBucketVersioning"
    assert versioning["Resource"] == f"arn:aws:s3:::{BUCKET}"


def test_missing_policy_is_put_then_verified(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        _no_policy(stubber)
        stubber.add_response("put_bucket_policy", {}, {"Bucket": BUCKET, "Policy": _doc()})
        stubber.add_response("get_bucket_policy", {"Policy": _doc()}, PARAMS)
        assert ensure_write_once_policy(client, BUCKET) is True
        stubber.assert_no_pending_responses()


def test_equivalent_existing_policy_is_not_rewritten(client: BaseClient) -> None:
    # SeaweedFS may return Resource as a string or list and reorder statements.
    reordered = write_once_policy(BUCKET)
    reordered["Statement"].reverse()
    reordered["Statement"][1]["Resource"] = [f"arn:aws:s3:::{BUCKET}/*"]
    with Stubber(client) as stubber:
        stubber.add_response("get_bucket_policy", {"Policy": json.dumps(reordered)}, PARAMS)
        assert ensure_write_once_policy(client, BUCKET) is False
        stubber.assert_no_pending_responses()  # no put


def test_different_policy_is_replaced(client: BaseClient) -> None:
    other = json.dumps({"Version": "2012-10-17", "Statement": []})
    with Stubber(client) as stubber:
        stubber.add_response("get_bucket_policy", {"Policy": other}, PARAMS)
        stubber.add_response("put_bucket_policy", {}, {"Bucket": BUCKET, "Policy": _doc()})
        stubber.add_response("get_bucket_policy", {"Policy": _doc()}, PARAMS)
        assert ensure_write_once_policy(client, BUCKET) is True
        stubber.assert_no_pending_responses()


def test_readback_mismatch_is_an_error(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        _no_policy(stubber)
        stubber.add_response("put_bucket_policy", {}, {"Bucket": BUCKET, "Policy": _doc()})
        stubber.add_response("get_bucket_policy", {"Policy": json.dumps({"Statement": []})}, PARAMS)
        with pytest.raises(RawBucketError, match="does not match"):
            ensure_write_once_policy(client, BUCKET)


def test_put_denied_is_an_error(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        _no_policy(stubber)
        stubber.add_client_error(
            "put_bucket_policy",
            "AccessDenied",
            http_status_code=403,
            expected_params={"Bucket": BUCKET, "Policy": _doc()},
        )
        with pytest.raises(RawBucketError, match="put_bucket_policy failed.*AccessDenied"):
            ensure_write_once_policy(client, BUCKET)


def test_get_transient_error_is_transient(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        stubber.add_client_error(
            "get_bucket_policy", "ServiceUnavailable", http_status_code=503, expected_params=PARAMS
        )
        with pytest.raises(RawBucketTransientError):
            ensure_write_once_policy(client, BUCKET)


def test_invalid_policy_json_is_an_error(client: BaseClient) -> None:
    with Stubber(client) as stubber:
        stubber.add_response("get_bucket_policy", {"Policy": "{not json"}, PARAMS)
        with pytest.raises(RawBucketError, match="not valid JSON"):
            ensure_write_once_policy(client, BUCKET)


def test_second_run_never_calls_put_bucket_versioning(client: BaseClient) -> None:
    """The policy denies PutBucketVersioning: an Enabled bucket must not trigger it again."""
    with Stubber(client) as stubber:
        stubber.add_response("head_bucket", {}, PARAMS)
        stubber.add_response("get_bucket_versioning", {"Status": "Enabled"}, PARAMS)
        result = ensure_versioned_bucket(client, BUCKET)
        stubber.add_response("get_bucket_policy", {"Policy": _doc()}, PARAMS)
        assert ensure_write_once_policy(client, BUCKET) is False
        stubber.assert_no_pending_responses()
    assert result.versioning_changed is False


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("Condition", {"StringEquals": {"aws:username": "x"}}),
        ("NotPrincipal", {"AWS": "arn:aws:iam::1:user/x"}),
        ("NotResource", "arn:aws:s3:::pits-raw/z"),
    ],
)
def test_same_sid_with_extra_key_is_rewritten(client: BaseClient, key: str, value: object) -> None:
    """A statement with the right Sid but an extra Condition/Not* key is not equivalent."""
    tampered = write_once_policy(BUCKET)
    tampered["Statement"][0][key] = value
    with Stubber(client) as stubber:
        stubber.add_response("get_bucket_policy", {"Policy": json.dumps(tampered)}, PARAMS)
        stubber.add_response("put_bucket_policy", {}, {"Bucket": BUCKET, "Policy": _doc()})
        stubber.add_response("get_bucket_policy", {"Policy": _doc()}, PARAMS)
        assert ensure_write_once_policy(client, BUCKET) is True
        stubber.assert_no_pending_responses()

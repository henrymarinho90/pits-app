"""Offline tests for pits.ingestion.raw_store (botocore Stubber + MemoryRawStore)."""

from __future__ import annotations

import io
from datetime import date, datetime

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import ConnectTimeoutError, ReadTimeoutError
from botocore.response import StreamingBody
from botocore.stub import Stubber

from pits.ingestion.raw_store import (
    MAX_OBJECT_BYTES,
    MemoryRawStore,
    RawObjectExistsError,
    RawObjectNotFoundError,
    RawStoreError,
    RawStoreTransientError,
    S3RawStore,
    batch_prefix,
)

BUCKET = "pits-raw"
BATCH = "0b6f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a10"


@pytest.fixture
def s3():
    client = boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        config=Config(retries={"max_attempts": 0}),
    )
    with Stubber(client) as stubber:
        yield client, stubber


def _client_error(stubber, method, code, status, expected=None):
    stubber.add_client_error(
        method, service_error_code=code, http_status_code=status, expected_params=expected
    )


def _put_params(key, body, content_type):
    return {
        "Bucket": BUCKET,
        "Key": key,
        "Body": body,
        "ContentType": content_type,
        "IfNoneMatch": "*",
    }


class _StubbedS3:
    """Wraps S3RawStore, pre-programming the Stubber to mimic a real bucket per call."""

    def __init__(self, inner, stubber):
        self._inner = inner
        self._stubber = stubber
        self._objects: dict[str, bytes] = {}

    def put_once(self, key, body, content_type):
        if len(body) <= MAX_OBJECT_BYTES:  # oversized bodies must make no S3 call
            expected = _put_params(key, body, content_type)
            if key in self._objects:
                _client_error(self._stubber, "put_object", "PreconditionFailed", 412, expected)
            else:
                self._stubber.add_response("put_object", {}, expected)
                self._objects[key] = body
        self._inner.put_once(key, body, content_type)

    def get(self, key):
        if key in self._objects:
            body = self._objects[key]
            self._stubber.add_response(
                "get_object",
                {"Body": StreamingBody(io.BytesIO(body), len(body))},
                {"Bucket": BUCKET, "Key": key},
            )
        else:
            _client_error(self._stubber, "get_object", "NoSuchKey", 404)
        return self._inner.get(key)


@pytest.fixture(params=["s3", "memory"])
def store(request, s3):
    """The same contract tests run against both implementations."""
    if request.param == "memory":
        return MemoryRawStore()
    client, stubber = s3
    return _StubbedS3(S3RawStore(client, BUCKET), stubber)


def test_put_then_get_roundtrip(store):
    store.put_once("a/b/payload.json", b"[1]", "application/json")
    assert store.get("a/b/payload.json") == b"[1]"


def test_put_twice_raises_exists_and_keeps_original(store):
    store.put_once("a/k.json", b"first", "application/json")
    with pytest.raises(RawObjectExistsError, match="a/k.json"):
        store.put_once("a/k.json", b"second", "application/json")
    assert store.get("a/k.json") == b"first"


def test_get_missing_raises_not_found(store):
    with pytest.raises(RawObjectNotFoundError, match="nope"):
        store.get("nope")


def test_memory_list_prefixes_with_delimiter():
    memory = MemoryRawStore()
    memory.put_once("ss/extraction_date=2026-10-10/batch_id=x/manifest.json", b"{}", "a/b")
    memory.put_once("ss/extraction_date=2026-10-10/batch_id=x/payload-00000.json", b"[]", "a/b")
    memory.put_once("ss/extraction_date=2026-10-09/batch_id=y/manifest.json", b"{}", "a/b")
    memory.put_once("other/extraction_date=2026-10-10/batch_id=z/manifest.json", b"{}", "a/b")
    assert memory.list_prefixes("ss/") == [
        "ss/extraction_date=2026-10-09/",
        "ss/extraction_date=2026-10-10/",
    ]
    assert memory.list_prefixes("ss/extraction_date=2026-10-10/") == [
        "ss/extraction_date=2026-10-10/batch_id=x/"
    ]
    assert memory.list_prefixes("missing/") == []


def test_s3_list_prefixes_uses_delimiter_and_returns_common_prefixes(s3):
    client, stubber = s3
    stubber.add_response(
        "list_objects_v2",
        {
            "IsTruncated": False,
            "CommonPrefixes": [
                {"Prefix": "ss/extraction_date=2026-10-09/"},
                {"Prefix": "ss/extraction_date=2026-10-10/"},
            ],
        },
        {"Bucket": BUCKET, "Prefix": "ss/", "Delimiter": "/"},
    )
    stubber.add_response(
        "list_objects_v2",
        {"IsTruncated": False},
        {"Bucket": BUCKET, "Prefix": "missing/", "Delimiter": "/"},
    )
    s3_store = S3RawStore(client, BUCKET)
    assert s3_store.list_prefixes("ss/") == [
        "ss/extraction_date=2026-10-09/",
        "ss/extraction_date=2026-10-10/",
    ]
    assert s3_store.list_prefixes("missing/") == []
    stubber.assert_no_pending_responses()


@pytest.mark.parametrize("operation", ["put_once", "get"])
def test_empty_key_rejected(store, operation):
    args = (b"x", "t/p") if operation == "put_once" else ()
    with pytest.raises(ValueError, match="key"):
        getattr(store, operation)("", *args)


def test_size_limit(store):
    store.put_once("ok.bin", b"x" * MAX_OBJECT_BYTES, "application/octet-stream")
    with pytest.raises(RawStoreError, match="big.bin"):
        store.put_once("big.bin", b"x" * (MAX_OBJECT_BYTES + 1), "application/octet-stream")


def test_s3_412_maps_to_exists_error(s3):
    client, stubber = s3
    _client_error(stubber, "put_object", "PreconditionFailed", 412, _put_params("k", b"x", "t/p"))
    with pytest.raises(RawObjectExistsError):
        S3RawStore(client, BUCKET).put_once("k", b"x", "t/p")
    stubber.assert_no_pending_responses()


def test_s3_other_errors_become_raw_store_error(s3):
    client, stubber = s3
    _client_error(stubber, "put_object", "AccessDenied", 403)
    with pytest.raises(RawStoreError, match="AccessDenied") as err:
        S3RawStore(client, BUCKET).put_once("k", b"x", "t/p")
    assert not isinstance(err.value, RawObjectExistsError)


def test_s3_size_limit_makes_no_call(s3):
    client, stubber = s3  # no responses queued: any call would fail
    with pytest.raises(RawStoreError, match="byte limit"):
        S3RawStore(client, BUCKET).put_once("k", b"x" * (MAX_OBJECT_BYTES + 1), "t/p")
    stubber.assert_no_pending_responses()


def test_s3_list_prefixes_paginates(s3):
    client, stubber = s3
    base = {"Bucket": BUCKET, "Prefix": "ss/", "Delimiter": "/"}
    stubber.add_response(
        "list_objects_v2",
        {
            "IsTruncated": True,
            "NextContinuationToken": "t1",
            "CommonPrefixes": [{"Prefix": "ss/extraction_date=2026-10-09/"}],
        },
        base,
    )
    stubber.add_response(
        "list_objects_v2",
        {"IsTruncated": False, "CommonPrefixes": [{"Prefix": "ss/extraction_date=2026-10-10/"}]},
        {**base, "ContinuationToken": "t1"},
    )
    assert S3RawStore(client, BUCKET).list_prefixes("ss/") == [
        "ss/extraction_date=2026-10-09/",
        "ss/extraction_date=2026-10-10/",
    ]
    stubber.assert_no_pending_responses()


def test_s3_list_error_is_typed(s3):
    client, stubber = s3
    _client_error(stubber, "list_objects_v2", "AccessDenied", 403)
    with pytest.raises(RawStoreError, match="AccessDenied"):
        S3RawStore(client, BUCKET).list_prefixes("ss/")


def test_memory_store_records_content_type():
    memory = MemoryRawStore()
    memory.put_once("k", b"x", "application/json")
    assert memory.content_types["k"] == "application/json"


def test_batch_prefix_layout():
    assert batch_prefix("superfinanciera_trm", date(2026, 10, 10), BATCH) == (
        f"superfinanciera_trm/extraction_date=2026-10-10/batch_id={BATCH}/"
    )


@pytest.mark.parametrize("source", ["", "Trm", "trm-x", "1trm", "trm/x", "trmé", "trm\n", " trm"])
def test_batch_prefix_rejects_bad_source_system(source):
    with pytest.raises(ValueError, match="source_system"):
        batch_prefix(source, date(2026, 10, 10), BATCH)


@pytest.mark.parametrize("batch_id", ["", "abc", BATCH.upper(), BATCH.replace("-", ""), "../x"])
def test_batch_prefix_rejects_bad_batch_id(batch_id):
    with pytest.raises(ValueError, match="batch_id"):
        batch_prefix("trm", date(2026, 10, 10), batch_id)


def test_batch_prefix_rejects_datetime():
    with pytest.raises(TypeError, match="datetime"):
        batch_prefix("trm", datetime(2026, 10, 10, 12, 0), BATCH)


class _FailingClient:
    """Fake S3 client whose calls raise botocore (non-ClientError) exceptions."""

    def __init__(self, error=None, body=None):
        self._error = error
        self._body = body

    def put_object(self, **kwargs):
        raise self._error

    def list_objects_v2(self, **kwargs):
        raise self._error

    def get_object(self, **kwargs):
        if self._error:
            raise self._error
        return {"Body": self._body}


class _BrokenBody:
    def read(self):
        raise ReadTimeoutError(endpoint_url="https://secret-host.test/pits-raw/k")


@pytest.mark.parametrize("operation", ["put_once", "list_prefixes", "get"])
def test_s3_botocore_errors_become_transient(operation):
    error = ConnectTimeoutError(endpoint_url="https://secret-host.test/pits-raw/k")
    s3_store = S3RawStore(_FailingClient(error=error), BUCKET)
    args = {"put_once": ("k", b"x", "t/p"), "list_prefixes": ("ss/",), "get": ("k",)}[operation]
    with pytest.raises(RawStoreTransientError, match="ConnectTimeoutError") as err:
        getattr(s3_store, operation)(*args)
    assert "secret-host" not in str(err.value)
    assert err.value.__cause__ is None


def test_s3_body_read_failure_becomes_transient():
    s3_store = S3RawStore(_FailingClient(body=_BrokenBody()), BUCKET)
    with pytest.raises(RawStoreTransientError, match="ReadTimeoutError") as err:
        s3_store.get("k")
    assert "secret-host" not in str(err.value)

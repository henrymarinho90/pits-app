"""Offline tests for the contract-test helpers (no S3 endpoint needed)."""

from typing import Any, cast

import pytest
from botocore.client import BaseClient
from s3_helpers import BucketFactory, SettingsError, load_settings, purge_bucket

BASE = {
    "S3_ENDPOINT_URL": "http://127.0.0.1:8333",
    "S3_ACCESS_KEY_ID": "key",
    "S3_SECRET_ACCESS_KEY": "secret",
}


def test_load_settings_defaults() -> None:
    s = load_settings({**BASE, "S3_REGION": ""})
    assert (s.region, s.large_mb) == ("us-east-1", 128)


def test_load_settings_happy_path_localhost_and_padded_mb() -> None:
    s = load_settings(
        {**BASE, "S3_ENDPOINT_URL": "http://localhost:8333", "S3_CONTRACT_LARGE_MB": " 200 "}
    )
    assert s.endpoint_url == "http://localhost:8333"
    assert s.large_mb == 200


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        "   ",
        "10.0.0.5:8333",
        "http://10.0.0.5:8333",
        "http://localhost.evil.com:8333",
        "127.0.0.1:8333",
        "ftp://127.0.0.1:8333",
    ],
)
def test_load_settings_rejects_bad_endpoint(endpoint: str) -> None:
    with pytest.raises(SettingsError):
        load_settings({**BASE, "S3_ENDPOINT_URL": endpoint})


@pytest.mark.parametrize("mb", ["abc", "50", "99"])
def test_load_settings_rejects_bad_large_mb(mb: str) -> None:
    with pytest.raises(SettingsError):
        load_settings({**BASE, "S3_CONTRACT_LARGE_MB": mb})


class _Paginator:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self._pages = pages

    def paginate(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return self._pages


class FakeClient:
    def __init__(
        self,
        uploads: list[dict[str, Any]] | None = None,
        version_pages: list[dict[str, Any]] | None = None,
        delete_errors: list[dict[str, Any]] | None = None,
    ) -> None:
        self.failing: set[str] = set()
        self.deleted: list[str] = []
        self.aborted: list[tuple[str, str]] = []
        self.delete_calls: list[list[dict[str, Any]]] = []
        self._pages = {
            "list_multipart_uploads": [{"Uploads": uploads or []}],
            "list_object_versions": version_pages or [{}],
        }
        self._delete_errors = delete_errors

    def create_bucket(self, **_kwargs: Any) -> None:
        pass

    def get_paginator(self, operation: str) -> _Paginator:
        return _Paginator(self._pages[operation])

    def abort_multipart_upload(self, Bucket: str, Key: str, UploadId: str) -> None:  # noqa: N803
        self.aborted.append((Key, UploadId))

    def delete_objects(self, Bucket: str, Delete: dict[str, Any]) -> dict[str, Any]:  # noqa: N803
        self.delete_calls.append(Delete["Objects"])
        return {"Errors": self._delete_errors} if self._delete_errors else {}

    def delete_bucket(self, Bucket: str) -> None:  # noqa: N803
        if Bucket in self.failing:
            raise OSError("boom")
        self.deleted.append(Bucket)


def _as_client(fake: FakeClient) -> BaseClient:
    return cast(BaseClient, fake)


def _page(versions: int = 0, markers: int = 0, with_id: bool = True) -> dict[str, Any]:
    def mk(i: int, prefix: str) -> dict[str, Any]:
        item: dict[str, Any] = {"Key": f"{prefix}{i}"}
        if with_id:
            item["VersionId"] = f"v{i}"
        return item

    return {
        "Versions": [mk(i, "k") for i in range(versions)],
        "DeleteMarkers": [mk(i, "m") for i in range(markers)],
    }


def _client_with_page(page: dict[str, Any], **kwargs: Any) -> FakeClient:
    return FakeClient(version_pages=[page], **kwargs)


def test_purge_aborts_multipart_and_deletes_versions_and_markers() -> None:
    uploads = [{"Key": "big", "UploadId": "u1"}, {"Key": "big2", "UploadId": "u2"}]
    client = _client_with_page(_page(versions=2, markers=1), uploads=uploads)
    purge_bucket(_as_client(client), "b")
    assert client.aborted == [("big", "u1"), ("big2", "u2")]
    assert len(client.delete_calls) == 1
    assert client.delete_calls[0] == [
        {"Key": "k0", "VersionId": "v0"},
        {"Key": "k1", "VersionId": "v1"},
        {"Key": "m0", "VersionId": "v0"},
    ]
    assert client.deleted == ["b"]


def test_purge_omits_missing_version_id() -> None:
    client = _client_with_page(_page(versions=1, with_id=False))
    purge_bucket(_as_client(client), "b")
    assert client.delete_calls == [[{"Key": "k0"}]]


def test_purge_raises_on_delete_errors() -> None:
    errors = [{"Key": f"k{i}", "Code": "AccessDenied"} for i in range(5)]
    client = _client_with_page(_page(versions=1), delete_errors=errors)
    with pytest.raises(RuntimeError) as exc_info:
        purge_bucket(_as_client(client), "b")
    assert str(exc_info.value).count("AccessDenied") == 3  # only the first 3 errors
    assert client.deleted == []


def test_purge_batches_by_1000() -> None:
    client = _client_with_page(_page(versions=1001))
    purge_bucket(_as_client(client), "b")
    assert [len(c) for c in client.delete_calls] == [1000, 1]
    assert client.deleted == ["b"]


def test_cleanup_continues_after_error_and_reports() -> None:
    client = FakeClient()
    factory = BucketFactory(_as_client(client))
    names = [factory() for _ in range(3)]
    client.failing.add(names[0])
    errors = factory.cleanup()
    assert client.deleted == names[1:]
    assert len(errors) == 1
    assert names[0] in errors[0]


def test_keep_excludes_bucket_from_cleanup() -> None:
    client = FakeClient()
    factory = BucketFactory(_as_client(client))
    kept, other = factory(), factory()
    factory.keep(kept)
    assert factory.cleanup() == []
    assert client.deleted == [other]

"""Offline tests for pits.storage.settings."""

import pytest

from pits.storage.settings import StorageConfigError, load_storage_settings

ENV = {
    "S3_ENDPOINT_URL": "http://127.0.0.1:8333",
    "S3_ACCESS_KEY_ID": "AKIDEXAMPLE0001",
    "S3_SECRET_ACCESS_KEY": "super-secret-value-123",
    "S3_RAW_BUCKET": "pits-raw",
}


def test_loads_valid_env_with_default_region() -> None:
    settings = load_storage_settings(ENV)
    assert settings.raw_bucket == "pits-raw"
    assert settings.region == "us-east-1"


def test_empty_region_falls_back_to_default() -> None:
    assert load_storage_settings({**ENV, "S3_REGION": ""}).region == "us-east-1"


def test_explicit_region_is_kept() -> None:
    assert load_storage_settings({**ENV, "S3_REGION": "us-west-2"}).region == "us-west-2"


@pytest.mark.parametrize(
    "missing", ["S3_ENDPOINT_URL", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_RAW_BUCKET"]
)
def test_missing_variable_is_named_without_values(missing: str) -> None:
    env = {k: v for k, v in ENV.items() if k != missing}
    with pytest.raises(StorageConfigError) as exc:
        load_storage_settings(env)
    assert missing in str(exc.value)
    assert ENV["S3_SECRET_ACCESS_KEY"] not in str(exc.value)


def test_blank_variable_counts_as_missing() -> None:
    with pytest.raises(StorageConfigError, match="S3_ACCESS_KEY_ID"):
        load_storage_settings({**ENV, "S3_ACCESS_KEY_ID": "   "})


@pytest.mark.parametrize("url", ["127.0.0.1:8333", "ftp://host", "http://", "not a url"])
def test_invalid_endpoint_rejected(url: str) -> None:
    with pytest.raises(StorageConfigError, match="S3_ENDPOINT_URL"):
        load_storage_settings({**ENV, "S3_ENDPOINT_URL": url})


@pytest.mark.parametrize(
    "bucket",
    [
        "ab",
        "Pits-Raw",
        "-pits",
        "pits-",
        "pits..raw",
        "192.168.0.1",
        "pits_raw",
        "a" * 64,
        "xn--pits",
        "sthree-pits",
        "amzn-s3-demo-pits",
        "pits-s3alias",
        "pits--ol-s3",
        "pits.mrap",
        "pits--x-s3",
        "pits--table-s3",
    ],
)
def test_invalid_bucket_rejected(bucket: str) -> None:
    with pytest.raises(StorageConfigError, match="S3_RAW_BUCKET"):
        load_storage_settings({**ENV, "S3_RAW_BUCKET": bucket})


def test_contract_prefix_rejected() -> None:
    with pytest.raises(StorageConfigError, match="pits-contract-"):
        load_storage_settings({**ENV, "S3_RAW_BUCKET": "pits-contract-abcd1234"})


def test_repr_hides_secret() -> None:
    assert ENV["S3_SECRET_ACCESS_KEY"] not in repr(load_storage_settings(ENV))


@pytest.mark.parametrize("bucket", ["abc", "a" * 63, "pits.raw"])
def test_valid_bucket_edges_accepted(bucket: str) -> None:
    assert load_storage_settings({**ENV, "S3_RAW_BUCKET": bucket}).raw_bucket == bucket


def test_endpoint_with_embedded_credentials_rejected_without_leaking_url() -> None:
    url = "http://user:hunter2@127.0.0.1:8333"
    with pytest.raises(StorageConfigError, match="must not embed credentials") as exc:
        load_storage_settings({**ENV, "S3_ENDPOINT_URL": url})
    assert "hunter2" not in str(exc.value)
    assert url not in str(exc.value)

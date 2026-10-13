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
    settings = load_storage_settings(ENV, identity="admin")
    assert settings.raw_bucket == "pits-raw"
    assert settings.region == "us-east-1"


def test_empty_region_falls_back_to_default() -> None:
    assert load_storage_settings({**ENV, "S3_REGION": ""}, identity="admin").region == "us-east-1"


def test_explicit_region_is_kept() -> None:
    assert (
        load_storage_settings({**ENV, "S3_REGION": "us-west-2"}, identity="admin").region
        == "us-west-2"
    )


@pytest.mark.parametrize(
    "missing", ["S3_ENDPOINT_URL", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_RAW_BUCKET"]
)
def test_missing_variable_is_named_without_values(missing: str) -> None:
    env = {k: v for k, v in ENV.items() if k != missing}
    with pytest.raises(StorageConfigError) as exc:
        load_storage_settings(env, identity="admin")
    assert missing in str(exc.value)
    assert ENV["S3_SECRET_ACCESS_KEY"] not in str(exc.value)


def test_blank_variable_counts_as_missing() -> None:
    with pytest.raises(StorageConfigError, match="S3_ACCESS_KEY_ID"):
        load_storage_settings({**ENV, "S3_ACCESS_KEY_ID": "   "}, identity="admin")


@pytest.mark.parametrize("url", ["127.0.0.1:8333", "ftp://host", "http://", "not a url"])
def test_invalid_endpoint_rejected(url: str) -> None:
    with pytest.raises(StorageConfigError, match="S3_ENDPOINT_URL"):
        load_storage_settings({**ENV, "S3_ENDPOINT_URL": url}, identity="admin")


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
        load_storage_settings({**ENV, "S3_RAW_BUCKET": bucket}, identity="admin")


def test_contract_prefix_rejected() -> None:
    with pytest.raises(StorageConfigError, match="pits-contract-"):
        load_storage_settings({**ENV, "S3_RAW_BUCKET": "pits-contract-abcd1234"}, identity="admin")


def test_repr_hides_secret() -> None:
    assert ENV["S3_SECRET_ACCESS_KEY"] not in repr(load_storage_settings(ENV, identity="admin"))


@pytest.mark.parametrize("bucket", ["abc", "a" * 63, "pits.raw"])
def test_valid_bucket_edges_accepted(bucket: str) -> None:
    assert (
        load_storage_settings({**ENV, "S3_RAW_BUCKET": bucket}, identity="admin").raw_bucket
        == bucket
    )


def test_endpoint_with_embedded_credentials_rejected_without_leaking_url() -> None:
    url = "http://user:hunter2@127.0.0.1:8333"
    with pytest.raises(StorageConfigError, match="must not embed credentials") as exc:
        load_storage_settings({**ENV, "S3_ENDPOINT_URL": url}, identity="admin")
    assert "hunter2" not in str(exc.value)
    assert url not in str(exc.value)


# --- D104(b): per-role identities ---

WRITER_KEY = "WRITERKEY0123456789"
READER_KEY = "READERKEY0123456789"
WRITER_SECRET = "writer-secret-0123456789-abcdefghijkl"
READER_SECRET = "reader-secret_0123456789-abcdefghijkl"
IDENTITY_ENV = {
    **ENV,
    "PITS_S3_WRITER_ACCESS_KEY_ID": WRITER_KEY,
    "PITS_S3_WRITER_SECRET_ACCESS_KEY": WRITER_SECRET,
    "PITS_S3_READER_ACCESS_KEY_ID": READER_KEY,
    "PITS_S3_READER_SECRET_ACCESS_KEY": READER_SECRET,
}


def test_each_identity_loads_its_own_credentials() -> None:
    assert load_storage_settings(IDENTITY_ENV, identity="admin").access_key_id == "AKIDEXAMPLE0001"
    writer = load_storage_settings(IDENTITY_ENV, identity="writer")
    assert (writer.access_key_id, writer.secret_access_key) == (WRITER_KEY, WRITER_SECRET)
    reader = load_storage_settings(IDENTITY_ENV, identity="reader")
    assert (reader.access_key_id, reader.secret_access_key) == (READER_KEY, READER_SECRET)


@pytest.mark.parametrize("identity", ["writer", "reader"])
def test_no_fallback_to_admin(identity: str) -> None:
    with pytest.raises(StorageConfigError) as exc:
        load_storage_settings(ENV, identity=identity)  # type: ignore[arg-type]
    assert f"PITS_S3_{identity.upper()}_ACCESS_KEY_ID" in str(exc.value)


@pytest.mark.parametrize("identity", ["writer", "reader"])
@pytest.mark.parametrize("part", ["ACCESS_KEY_ID", "SECRET_ACCESS_KEY"])
def test_missing_identity_variable_is_named_without_values(identity: str, part: str) -> None:
    name = f"PITS_S3_{identity.upper()}_{part}"
    env = {k: v for k, v in IDENTITY_ENV.items() if k != name}
    with pytest.raises(StorageConfigError) as exc:
        load_storage_settings(env, identity=identity)  # type: ignore[arg-type]
    assert name in str(exc.value)
    assert WRITER_SECRET not in str(exc.value) and READER_SECRET not in str(exc.value)


def test_admin_identity_does_not_need_the_others() -> None:
    assert load_storage_settings(ENV, identity="admin").access_key_id == "AKIDEXAMPLE0001"


def test_admin_credential_format_is_not_validated() -> None:
    env = {**ENV, "S3_ACCESS_KEY_ID": "ak", "S3_SECRET_ACCESS_KEY": "s"}
    assert load_storage_settings(env, identity="admin").access_key_id == "ak"


@pytest.mark.parametrize(
    ("part", "value"),
    [
        ("ACCESS_KEY_ID", "SHORT"),
        ("ACCESS_KEY_ID", "has-dash-0123456789"),
        ("ACCESS_KEY_ID", "A" * 129),
        ("SECRET_ACCESS_KEY", "short-secret"),
        ("SECRET_ACCESS_KEY", "has space " + "a" * 30),
        ("SECRET_ACCESS_KEY", "a" * 129),
    ],
)
@pytest.mark.parametrize("identity", ["writer", "reader"])
def test_invalid_identity_format_is_rejected_without_value(
    identity: str, part: str, value: str
) -> None:
    name = f"PITS_S3_{identity.upper()}_{part}"
    with pytest.raises(StorageConfigError) as exc:
        load_storage_settings({**IDENTITY_ENV, name: value}, identity=identity)  # type: ignore[arg-type]
    assert name in str(exc.value) and value not in str(exc.value)


@pytest.mark.parametrize(
    ("identity", "other_var"),
    [
        ("writer", "S3_ACCESS_KEY_ID"),
        ("writer", "PITS_S3_READER_ACCESS_KEY_ID"),
        ("reader", "S3_ACCESS_KEY_ID"),
        ("reader", "PITS_S3_WRITER_ACCESS_KEY_ID"),
    ],
)
def test_access_keys_must_differ_when_both_present(identity: str, other_var: str) -> None:
    own = f"PITS_S3_{identity.upper()}_ACCESS_KEY_ID"
    env = {**IDENTITY_ENV, other_var: IDENTITY_ENV[own]}
    with pytest.raises(StorageConfigError) as exc:
        load_storage_settings(env, identity=identity)  # type: ignore[arg-type]
    assert own in str(exc.value) and other_var in str(exc.value)


def test_unknown_identity_is_rejected() -> None:
    with pytest.raises(StorageConfigError):
        load_storage_settings(IDENTITY_ENV, identity="root")  # type: ignore[arg-type]


def test_repr_hides_identity_secret() -> None:
    assert WRITER_SECRET not in repr(load_storage_settings(IDENTITY_ENV, identity="writer"))


def test_identity_is_required() -> None:
    with pytest.raises(TypeError):
        load_storage_settings(ENV)  # type: ignore[call-arg]

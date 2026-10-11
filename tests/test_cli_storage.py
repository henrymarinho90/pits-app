"""Offline tests for `pits storage` using CliRunner and a Stubber-backed client."""

import pytest
from botocore.client import BaseClient
from botocore.exceptions import EndpointConnectionError
from botocore.stub import Stubber
from typer.testing import CliRunner

import pits
from pits.cli import app
from pits.storage import cli as storage_cli
from pits.storage.client import build_s3_client
from pits.storage.settings import StorageSettings

runner = CliRunner()

SECRET = "cli-test-secret-value-xyz"
ENV = {
    "S3_ENDPOINT_URL": "http://127.0.0.1:9",
    "S3_ACCESS_KEY_ID": "AKIDEXAMPLE0001",
    "S3_SECRET_ACCESS_KEY": SECRET,
    "S3_RAW_BUCKET": "pits-raw",
}
BUCKET = {"Bucket": "pits-raw"}
NORM = {"Bucket": "pits-normalized"}  # default (D74)
NORM_ENABLE = {"Bucket": "pits-normalized", "VersioningConfiguration": {"Status": "Enabled"}}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [*ENV, "S3_REGION", "S3_NORMALIZED_BUCKET"]:
        monkeypatch.delenv(name, raising=False)


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)


def _use_client(monkeypatch: pytest.MonkeyPatch, client: BaseClient) -> None:
    monkeypatch.setattr(storage_cli, "client_factory", lambda settings: client)


def _real_client() -> BaseClient:
    return build_s3_client(
        StorageSettings(
            ENV["S3_ENDPOINT_URL"],
            ENV["S3_ACCESS_KEY_ID"],
            SECRET,
            "us-east-1",
            ENV["S3_RAW_BUCKET"],
        )
    )


def test_init_creates_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    client = _real_client()
    _use_client(monkeypatch, client)
    with Stubber(client) as stubber:
        stubber.add_client_error("head_bucket", "404", http_status_code=404, expected_params=BUCKET)
        stubber.add_response("create_bucket", {}, BUCKET)
        stubber.add_response("get_bucket_versioning", {}, BUCKET)
        stubber.add_response(
            "put_bucket_versioning",
            {},
            {"Bucket": "pits-raw", "VersioningConfiguration": {"Status": "Enabled"}},
        )
        stubber.add_response("get_bucket_versioning", {"Status": "Enabled"}, BUCKET)
        stubber.add_client_error("head_bucket", "404", http_status_code=404, expected_params=NORM)
        stubber.add_response("create_bucket", {}, NORM)
        stubber.add_response("get_bucket_versioning", {}, NORM)
        stubber.add_response("put_bucket_versioning", {}, NORM_ENABLE)
        stubber.add_response("get_bucket_versioning", {"Status": "Enabled"}, NORM)
        result = runner.invoke(app, ["storage", "init"])
        stubber.assert_no_pending_responses()
    assert result.exit_code == 0
    assert result.stdout == (
        "bucket=pits-raw created=true versioning=Enabled changed=true\n"
        "bucket=pits-normalized created=true versioning=Enabled changed=true\n"
    )
    assert result.stderr == ""


def test_init_is_idempotent_output(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    client = _real_client()
    _use_client(monkeypatch, client)
    with Stubber(client) as stubber:
        stubber.add_response("head_bucket", {}, BUCKET)
        stubber.add_response("get_bucket_versioning", {"Status": "Enabled"}, BUCKET)
        stubber.add_response("head_bucket", {}, NORM)
        stubber.add_response("get_bucket_versioning", {"Status": "Enabled"}, NORM)
        result = runner.invoke(app, ["storage", "init"])
        stubber.assert_no_pending_responses()
    assert result.exit_code == 0
    first, second = result.stdout.splitlines(keepends=True)
    assert first == "bucket=pits-raw created=false versioning=Enabled changed=false\n"  # unchanged
    assert second == "bucket=pits-normalized created=false versioning=Enabled changed=false\n"
    assert result.stderr == ""


def test_init_uses_s3_normalized_bucket_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    monkeypatch.setenv("S3_NORMALIZED_BUCKET", "my-norm")
    client = _real_client()
    _use_client(monkeypatch, client)
    custom = {"Bucket": "my-norm"}
    with Stubber(client) as stubber:
        stubber.add_response("head_bucket", {}, BUCKET)
        stubber.add_response("get_bucket_versioning", {"Status": "Enabled"}, BUCKET)
        stubber.add_response("head_bucket", {}, custom)
        stubber.add_response("get_bucket_versioning", {"Status": "Enabled"}, custom)
        result = runner.invoke(app, ["storage", "init"])
        stubber.assert_no_pending_responses()
    assert result.exit_code == 0
    assert result.stdout.splitlines()[1].startswith("bucket=my-norm ")


def test_init_normalized_suspended_fails_after_raw_line(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    client = _real_client()
    _use_client(monkeypatch, client)
    with Stubber(client) as stubber:
        stubber.add_response("head_bucket", {}, BUCKET)
        stubber.add_response("get_bucket_versioning", {"Status": "Enabled"}, BUCKET)
        stubber.add_response("head_bucket", {}, NORM)
        stubber.add_response("get_bucket_versioning", {"Status": "Suspended"}, NORM)
        result = runner.invoke(app, ["storage", "init"])
        stubber.assert_no_pending_responses()
    assert result.exit_code == 1
    assert result.stdout == "bucket=pits-raw created=false versioning=Enabled changed=false\n"
    assert "Suspended" in result.stderr and "pits-normalized" in result.stderr
    assert SECRET not in result.stdout + result.stderr


def test_init_without_variables_fails_naming_variable() -> None:
    result = runner.invoke(app, ["storage", "init"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.startswith("error: ")
    assert "S3_ENDPOINT_URL" in result.stderr
    assert "Traceback" not in result.stderr


def test_init_bucket_error_exits_1_without_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    client = _real_client()
    _use_client(monkeypatch, client)
    with Stubber(client) as stubber:
        stubber.add_response("head_bucket", {}, BUCKET)
        stubber.add_response("get_bucket_versioning", {"Status": "Suspended"}, BUCKET)
        result = runner.invoke(app, ["storage", "init"])
        stubber.assert_no_pending_responses()
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.startswith("error: ")
    assert "Suspended" in result.stderr
    assert SECRET not in result.stdout and SECRET not in result.stderr


def test_init_connection_error_exits_1_without_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)

    def failing_factory(settings: StorageSettings) -> BaseClient:
        raise EndpointConnectionError(endpoint_url=f"{settings.endpoint_url}?k={SECRET}")

    monkeypatch.setattr(storage_cli, "client_factory", failing_factory)
    result = runner.invoke(app, ["storage", "init"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.startswith("error: ")
    assert "EndpointConnectionError" in result.stderr
    assert SECRET not in result.stdout and SECRET not in result.stderr
    assert "Traceback" not in result.stderr


def test_storage_help_lists_init() -> None:
    result = runner.invoke(app, ["storage", "--help"])
    assert result.exit_code == 0
    assert "init" in result.output


def test_version_command_unchanged() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.output.strip() == pits.__version__

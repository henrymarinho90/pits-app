"""Offline tests for `pits normalize trm` (Stubber client for bucket checks, memory stores)."""

from __future__ import annotations

import re
from datetime import date

import httpx
import pytest
from botocore.client import BaseClient
from botocore.exceptions import EndpointConnectionError, InvalidRegionError
from botocore.stub import Stubber
from runt_support import B2, put_runt_batch, raw_row
from soda_fake import contiguous_rows, extract_batch
from typer.testing import CliRunner

from pits.cli import app
from pits.ingestion.raw_store import MemoryRawStore, RawStoreTransientError
from pits.normalized import cli as normalize_cli
from pits.storage.client import build_s3_client
from pits.storage.settings import StorageSettings

runner = CliRunner()

SECRET = "cli-normalize-secret-xyz-0123456789"
ENV = {
    "S3_ENDPOINT_URL": "http://127.0.0.1:9",
    "PITS_S3_WRITER_ACCESS_KEY_ID": "WRITERKEYEXAMPLE0001",
    "PITS_S3_WRITER_SECRET_ACCESS_KEY": SECRET,
    "S3_RAW_BUCKET": "pits-raw",
    "S3_NORMALIZED_BUCKET": "pits-norm",
}
B1 = "0b6f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a10"
NORM = {"Bucket": "pits-norm"}
BASE = "fx_rate/source_system=superfinanciera_trm/inputs_until=2026-10-10/"
LINE = re.compile(
    r"outcome=(created|already_present) fingerprint=([0-9a-f]{64}) inputs=1 baseline="
    + B1
    + r" rows=34 coverage=1991-12-02\.\.1992-01-04 "
    + r"csv=s3://pits-norm/"
    + re.escape(BASE)
    + r"fingerprint=\2/fx_rate\.csv "
    + r"manifest=s3://pits-norm/"
    + re.escape(BASE)
    + r"fingerprint=\2/manifest\.json\n"
)


class World:
    def __init__(self, client: BaseClient) -> None:
        self.client = client
        self.raw = MemoryRawStore()
        self.norm = MemoryRawStore()
        self.buckets_seen: list[str] = []

    def store(self, client: BaseClient, bucket: str) -> MemoryRawStore:
        self.buckets_seen.append(bucket)
        return self.raw if bucket == "pits-raw" else self.norm


def _client() -> BaseClient:
    return build_s3_client(
        StorageSettings(
            ENV["S3_ENDPOINT_URL"], ENV["PITS_S3_WRITER_ACCESS_KEY_ID"], SECRET, "us-east-1", "x"
        )
    )


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    for name in ("S3_REGION", "SODA_APP_TOKEN", "SODA_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    w = World(_client())
    monkeypatch.setattr(normalize_cli, "client_factory", lambda settings: w.client)
    monkeypatch.setattr(normalize_cli, "store_factory", w.store)
    extract_batch(w.raw, contiguous_rows(), batch_id=B1, day=date(2026, 10, 10))
    return w


def _run(world: World, *args: str):
    with Stubber(world.client) as stubber:
        stubber.add_response("head_bucket", {}, NORM)
        stubber.add_response("get_bucket_versioning", {"Status": "Enabled"}, NORM)
        result = runner.invoke(app, ["normalize", "trm", *args])
        stubber.assert_no_pending_responses()
    return result


def test_success_exact_stdout_then_already_present(world: World) -> None:
    first = _run(world)
    assert first.exit_code == 0, first.stderr
    m = LINE.fullmatch(first.stdout)
    assert m and m.group(1) == "created"
    assert first.stderr == ""
    second = _run(world)
    assert second.exit_code == 0
    assert second.stdout == first.stdout.replace("outcome=created", "outcome=already_present")
    assert second.stderr == ""
    assert len(world.norm.objects) == 2
    assert "pits-norm" in world.buckets_seen and "pits-raw" in world.buckets_seen


def test_range_warning_goes_to_stderr_without_failing(world: World) -> None:
    result = _run(world, "--warn-range-days", "3")
    assert result.exit_code == 0
    assert "warning:" in result.stderr and "4 days" in result.stderr
    assert LINE.fullmatch(result.stdout)
    assert "warning" not in result.stdout


def test_no_warning_at_or_below_threshold(world: World) -> None:
    assert _run(world, "--warn-range-days", "4").stderr == ""


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_invalid_warn_range_days_is_usage_error(world: World, value: str) -> None:
    result = runner.invoke(app, ["normalize", "trm", "--warn-range-days", value])
    assert result.exit_code == 2
    assert result.stdout == ""


def test_missing_full_batch_is_permanent_exit_1(world: World) -> None:
    world.raw.objects.clear()
    result = _run(world)
    assert result.exit_code == 1
    assert result.stdout == "" and result.stderr.startswith("error: ")
    assert "Traceback" not in result.stderr


def test_transient_error_exits_3(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(prefix: str) -> list[str]:
        raise RawStoreTransientError("simulated network failure")

    monkeypatch.setattr(world.raw, "list_prefixes", boom)
    result = _run(world)
    assert result.exit_code == 3
    assert result.stdout == "" and result.stderr == "error: simulated network failure\n"


def test_conflicting_existing_csv_exits_1(world: World) -> None:
    first = _run(world)
    csv_key = next(k for k in world.norm.objects if k.endswith("fx_rate.csv"))
    manifest_key = next(k for k in world.norm.objects if k.endswith("manifest.json"))
    del world.norm.objects[manifest_key]
    world.norm.objects[csv_key] = b"tampered"
    result = _run(world)
    assert first.exit_code == 0
    assert result.exit_code == 1
    assert result.stderr.startswith("error: ") and result.stdout == ""


def test_missing_bucket_exits_1_and_does_not_create(world: World) -> None:
    with Stubber(world.client) as stubber:
        stubber.add_client_error("head_bucket", "404", http_status_code=404, expected_params=NORM)
        result = runner.invoke(app, ["normalize", "trm"])
        stubber.assert_no_pending_responses()  # no create_bucket was attempted
    assert result.exit_code == 1
    assert result.stdout == "" and "does not exist" in result.stderr
    assert "pits storage init" in result.stderr
    assert world.norm.objects == {}


@pytest.mark.parametrize("status", [None, "Suspended"])
def test_bucket_without_enabled_versioning_exits_1(world: World, status: str | None) -> None:
    with Stubber(world.client) as stubber:
        stubber.add_response("head_bucket", {}, NORM)
        stubber.add_response("get_bucket_versioning", {"Status": status} if status else {}, NORM)
        result = runner.invoke(app, ["normalize", "trm"])
        stubber.assert_no_pending_responses()
    assert result.exit_code == 1
    assert "Versioning" in result.stderr and world.norm.objects == {}


def test_missing_variables_exit_1_naming_variable(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("S3_ENDPOINT_URL")
    result = runner.invoke(app, ["normalize", "trm"])
    assert result.exit_code == 1
    assert "S3_ENDPOINT_URL" in result.stderr and result.stdout == ""


def test_normalized_bucket_equal_to_raw_exits_1(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("S3_NORMALIZED_BUCKET", "pits-raw")
    result = runner.invoke(app, ["normalize", "trm"])
    assert result.exit_code == 1 and "must differ" in result.stderr


def test_client_construction_error_exits_1_without_secret(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing(settings: StorageSettings) -> BaseClient:
        raise EndpointConnectionError(endpoint_url=f"{settings.endpoint_url}?k={SECRET}")

    monkeypatch.setattr(normalize_cli, "client_factory", failing)
    result = runner.invoke(app, ["normalize", "trm"])
    assert result.exit_code == 1
    assert "EndpointConnectionError" in result.stderr
    assert SECRET not in result.stdout + result.stderr and "Traceback" not in result.stderr


def test_bucket_check_connection_error_exits_3_without_secret(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(**kwargs: object) -> None:
        raise EndpointConnectionError(endpoint_url=f"http://x/?k={SECRET}")

    monkeypatch.setattr(world.client, "head_bucket", refuse)
    result = runner.invoke(app, ["normalize", "trm"])
    assert result.exit_code == 3
    assert SECRET not in result.stdout + result.stderr and "Traceback" not in result.stderr


@pytest.mark.parametrize("code", ["503", "InternalError", "SlowDown"])
def test_bucket_check_transient_error_exits_3(world: World, code: str) -> None:
    status = 503 if code in ("503", "SlowDown") else 500
    with Stubber(world.client) as stubber:
        stubber.add_client_error("head_bucket", code, http_status_code=status, expected_params=NORM)
        result = runner.invoke(app, ["normalize", "trm"])
        stubber.assert_no_pending_responses()
    assert result.exit_code == 3
    assert result.stdout == "" and result.stderr.startswith("error: ")
    assert SECRET not in result.stdout + result.stderr and "Traceback" not in result.stderr
    assert world.norm.objects == {}


def test_invalid_region_with_real_factory_exits_1_without_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("S3_REGION", "bad region!")
    monkeypatch.setattr(normalize_cli, "client_factory", build_s3_client)
    result = runner.invoke(app, ["normalize", "trm"])
    assert result.exit_code == 1
    assert SECRET not in result.stdout + result.stderr and "Traceback" not in result.stderr
    assert InvalidRegionError.__name__ in result.stderr


def test_secrets_never_printed_on_success(world: World) -> None:
    result = _run(world, "--warn-range-days", "3")
    assert SECRET not in result.stdout + result.stderr
    assert ENV["PITS_S3_WRITER_ACCESS_KEY_ID"] not in result.stdout + result.stderr


def test_normalize_never_calls_soda_and_needs_no_soda_variables(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(self: httpx.Client, *args: object, **kwargs: object) -> httpx.Response:
        raise AssertionError("normalize must not perform HTTP requests")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    result = _run(world)  # no SODA_* variables are set by the fixture
    assert result.exit_code == 0, result.stderr


def test_help_lists_trm_and_group_is_registered() -> None:
    top = runner.invoke(app, ["--help"])
    assert "normalize" in top.output
    result = runner.invoke(app, ["normalize", "--help"])
    assert result.exit_code == 0 and "trm" in result.output


RUNT_LINE = re.compile(
    r"outcome=(created|already_present) publication=(\d{4}-\d{2}) fingerprint=([0-9a-f]{64}) "
    r"inputs=1 batch=([0-9a-f-]{36}) rows=(\d+) parts=(\d+) manifest=s3://pits-norm/"
    r"vehicle_fleet_snapshot/source_system=mintransporte_runt_parque/"
    r"publication_month=\2/fingerprint=\3/manifest\.json\n"
)


def _run_runt(world: World, *args: str):
    with Stubber(world.client) as stubber:
        stubber.add_response("head_bucket", {}, NORM)
        stubber.add_response("get_bucket_versioning", {"Status": "Enabled"}, NORM)
        result = runner.invoke(app, ["normalize", "runt", *args])
        stubber.assert_no_pending_responses()
    return result


def _runt_rows(n: int = 3, **over: str):
    return [raw_row(i, **over) for i in range(n)]


def test_runt_success_exact_stdout_then_already_present(world: World) -> None:
    put_runt_batch(world.raw, B1, date(2026, 10, 12), _runt_rows())
    first = _run_runt(world)
    assert first.exit_code == 0, first.stderr
    m = RUNT_LINE.fullmatch(first.stdout)
    assert m and m.group(1, 2, 4, 5, 6) == ("created", "2026-10", B1, "3", "1")
    assert first.stderr == ""
    second = _run_runt(world)
    assert second.exit_code == 0 and second.stderr == ""
    assert second.stdout == first.stdout.replace("outcome=created", "outcome=already_present")
    assert len(world.norm.objects) == 2  # one part + manifest


def test_runt_prints_one_line_per_publication(world: World) -> None:
    put_runt_batch(
        world.raw, B1, date(2026, 9, 12), _runt_rows(3, year=2026, month=9), year=2026, month=9
    )
    put_runt_batch(world.raw, B2, date(2026, 10, 12), _runt_rows(), year=2026, month=10)
    result = _run_runt(world)
    assert result.exit_code == 0
    lines = result.stdout.splitlines(keepends=True)
    assert [RUNT_LINE.fullmatch(x).group(2) for x in lines] == ["2026-09", "2026-10"]


def test_runt_invalid_value_exits_1_after_printing_the_committed_publications(
    world: World,
) -> None:
    put_runt_batch(
        world.raw, B1, date(2026, 9, 12), _runt_rows(3, year=2026, month=9), year=2026, month=9
    )
    bad = _runt_rows(2, nombre_municipio=" X")
    put_runt_batch(world.raw, B2, date(2026, 10, 12), bad, year=2026, month=10)
    result = _run_runt(world)
    assert result.exit_code == 1
    assert RUNT_LINE.fullmatch(result.stdout) and "publication=2026-09" in result.stdout
    assert result.stderr.startswith("error: ") and "Traceback" not in result.stderr
    assert " X" not in result.stderr


def test_runt_without_raw_batches_exits_1(world: World) -> None:
    result = _run_runt(world)
    assert result.exit_code == 1 and result.stdout == ""
    assert "No committed raw RUNT batch" in result.stderr


def test_runt_transient_error_exits_3(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(prefix: str) -> list[str]:
        raise RawStoreTransientError("simulated network failure")

    monkeypatch.setattr(world.raw, "list_prefixes", boom)
    result = _run_runt(world)
    assert result.exit_code == 3
    assert result.stdout == "" and result.stderr == "error: simulated network failure\n"


def test_runt_unknown_option_is_usage_error(world: World) -> None:
    result = runner.invoke(app, ["normalize", "runt", "--nope"])
    assert result.exit_code == 2 and result.stdout == ""


def test_runt_missing_variables_exit_1(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("S3_ENDPOINT_URL")
    result = runner.invoke(app, ["normalize", "runt"])
    assert result.exit_code == 1 and "S3_ENDPOINT_URL" in result.stderr


@pytest.mark.parametrize("command", ["trm", "runt"])
def test_normalize_does_not_fall_back_to_admin(
    world: World, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    for name in ("PITS_S3_WRITER_ACCESS_KEY_ID", "PITS_S3_WRITER_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name)
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "ADMINKEYEXAMPLE0001")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", SECRET)
    result = runner.invoke(app, ["normalize", command])
    assert result.exit_code == 1 and result.stdout == ""
    assert "PITS_S3_WRITER_ACCESS_KEY_ID" in result.stderr
    assert SECRET not in result.stdout + result.stderr

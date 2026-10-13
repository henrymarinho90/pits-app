"""Offline tests for `pits normalize divipola` (Stubber client for bucket checks, memory stores)."""

from __future__ import annotations

import re
from datetime import date

import pytest
from botocore.stub import Stubber
from divipola_support import B1, put_divipola_batch, raw_row, rows
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
NORM = {"Bucket": "pits-norm"}
LINE = re.compile(
    r"outcome=(created|already_present) rows_updated=2025-01-24 fingerprint=([0-9a-f]{64}) "
    + "batch="
    + B1
    + r" rows=3 manifest=s3://pits-norm/divipola_municipality/source_system=dane_divipola/"
    r"rows_updated=2025-01-24/fingerprint=\2/manifest\.json\n"
)


class World:
    def __init__(self) -> None:
        self.client = build_s3_client(
            StorageSettings(
                ENV["S3_ENDPOINT_URL"],
                ENV["PITS_S3_WRITER_ACCESS_KEY_ID"],
                SECRET,
                "us-east-1",
                "x",
            )
        )
        self.raw = MemoryRawStore()
        self.norm = MemoryRawStore()

    def store(self, client, bucket: str) -> MemoryRawStore:
        return self.raw if bucket == "pits-raw" else self.norm


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    for name in ("S3_REGION", "SODA_APP_TOKEN", "SODA_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    w = World()
    monkeypatch.setattr(normalize_cli, "client_factory", lambda settings: w.client)
    monkeypatch.setattr(normalize_cli, "store_factory", w.store)
    return w


def run(world: World, *args: str):
    with Stubber(world.client) as stubber:
        stubber.add_response("head_bucket", {}, NORM)
        stubber.add_response("get_bucket_versioning", {"Status": "Enabled"}, NORM)
        result = runner.invoke(app, ["normalize", "divipola", *args])
        stubber.assert_no_pending_responses()
    return result


def test_success_exact_stdout_then_already_present(world: World) -> None:
    put_divipola_batch(world.raw, B1, date(2026, 10, 13), rows(3))
    first = run(world)
    assert first.exit_code == 0, first.stderr
    m = LINE.fullmatch(first.stdout)
    assert m and m.group(1) == "created" and first.stderr == ""
    second = run(world)
    assert second.exit_code == 0 and second.stderr == ""
    assert second.stdout == first.stdout.replace("outcome=created", "outcome=already_present")
    assert len(world.norm.objects) == 2  # csv + manifest


def test_invalid_value_exits_1_without_leaking_data(world: World) -> None:
    put_divipola_batch(world.raw, B1, date(2026, 10, 13), [*rows(2), raw_row(9, nom_mpio=" X")])
    result = run(world)
    assert result.exit_code == 1 and result.stdout == ""
    assert result.stderr.startswith("error: ") and "Traceback" not in result.stderr
    assert " X" not in result.stderr and world.norm.objects == {}


def test_without_raw_batches_exits_1(world: World) -> None:
    result = run(world)
    assert result.exit_code == 1 and result.stdout == ""
    assert "No committed raw DIVIPOLA batch" in result.stderr


def test_transient_error_exits_3(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(prefix: str) -> list[str]:
        raise RawStoreTransientError("simulated network failure")

    monkeypatch.setattr(world.raw, "list_prefixes", boom)
    result = run(world)
    assert result.exit_code == 3
    assert result.stdout == "" and result.stderr == "error: simulated network failure\n"


def test_unknown_option_is_usage_error(world: World) -> None:
    result = runner.invoke(app, ["normalize", "divipola", "--nope"])
    assert result.exit_code == 2 and result.stdout == ""


def test_does_not_fall_back_to_admin(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("PITS_S3_WRITER_ACCESS_KEY_ID", "PITS_S3_WRITER_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name)
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "ADMINKEYEXAMPLE0001")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", SECRET)
    result = runner.invoke(app, ["normalize", "divipola"])
    assert result.exit_code == 1 and result.stdout == ""
    assert "PITS_S3_WRITER_ACCESS_KEY_ID" in result.stderr

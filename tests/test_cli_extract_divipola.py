"""Offline tests for `pits extract divipola` (store and SODA replaced through the CLI seams)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from divipola_support import B1, B2, COLUMNS, FakeDivipola, rows
from typer.testing import CliRunner

from pits.cli import app
from pits.ingestion.manifest import Manifest
from pits.ingestion.raw_store import MemoryRawStore
from pits.sources import cli as extract_cli

runner = CliRunner()

TOKEN = "soda-test-token-value-xyz"
S3_SECRET = "cli-extract-s3-secret-xyz-0123456789"
ENV = {
    "S3_ENDPOINT_URL": "http://127.0.0.1:9",
    "PITS_S3_WRITER_ACCESS_KEY_ID": "WRITERKEYEXAMPLE0001",
    "PITS_S3_WRITER_SECRET_ACCESS_KEY": S3_SECRET,
    "S3_RAW_BUCKET": "pits-raw",
}
PREFIX = "dane_divipola/extraction_date=2026-10-13"


class World:
    def __init__(self) -> None:
        self.fake = FakeDivipola(rows(4))
        self.store = MemoryRawStore()
        self.batch_ids = [B1, B2]


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    w = World()
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("SODA_APP_TOKEN", TOKEN)
    monkeypatch.delenv("SODA_BASE_URL", raising=False)
    monkeypatch.delenv("S3_NORMALIZED_BUCKET", raising=False)
    monkeypatch.setattr(extract_cli, "client_factory", lambda settings: object())
    monkeypatch.setattr(extract_cli, "store_factory", lambda client, bucket: w.store)
    monkeypatch.setattr(extract_cli, "soda_factory", lambda s: w.fake.client(s.app_token))
    monkeypatch.setattr(extract_cli, "clock", lambda: datetime(2026, 10, 13, 12, tzinfo=UTC))
    monkeypatch.setattr(extract_cli, "batch_id_factory", lambda: w.batch_ids.pop(0))
    return w


def manifest_path(batch_id: str) -> str:
    return f"{PREFIX}/batch_id={batch_id}/manifest.json"


def test_commits_with_exact_output(world: World) -> None:
    result = runner.invoke(app, ["extract", "divipola"])
    assert result.exit_code == 0, result.stderr
    assert result.stdout == (
        f"outcome=committed batch_id={B1} rows_updated=2025-01-24 rows=4 files=1 "
        f"manifest=s3://pits-raw/{manifest_path(B1)}\n"
    )
    assert result.stderr == ""
    manifest = Manifest.from_json(world.store.get(manifest_path(B1)))
    assert manifest.app_token_used is True and manifest.watermark.column == "rowsUpdatedAt"


def test_second_run_is_unchanged_and_force_creates_batch(world: World) -> None:
    assert runner.invoke(app, ["extract", "divipola"]).exit_code == 0
    before = set(world.store.objects)
    second = runner.invoke(app, ["extract", "divipola"])
    assert second.exit_code == 0, second.stderr
    assert second.stdout.startswith(f"outcome=unchanged batch_id={B1} ")
    assert set(world.store.objects) == before
    forced = runner.invoke(app, ["extract", "divipola", "--force"])
    assert forced.exit_code == 0, forced.stderr
    assert forced.stdout.startswith(f"outcome=committed batch_id={B2} ")


def test_schema_drift_exit_1(world: World) -> None:
    world.fake.columns = COLUMNS[:-1]
    result = runner.invoke(app, ["extract", "divipola"])
    assert result.exit_code == 1
    assert result.stdout == "" and result.stderr.startswith("error: ")
    assert world.store.objects == {}
    assert TOKEN not in result.stdout + result.stderr


def test_truncation_exit_3(world: World) -> None:
    world.fake.total_override = 9
    result = runner.invoke(app, ["extract", "divipola"])
    assert result.exit_code == 3 and "Truncated" in result.stderr
    assert TOKEN not in result.stdout + result.stderr


def test_http_503_exit_3(world: World) -> None:
    world.fake.status = 503
    result = runner.invoke(app, ["extract", "divipola"])
    assert result.exit_code == 3 and result.stdout == ""
    assert TOKEN not in result.stdout + result.stderr


def test_invalid_storage_config_exit_1(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("S3_RAW_BUCKET", raising=False)
    monkeypatch.setenv("S3_NORMALIZED_BUCKET", "pits-raw")
    result = runner.invoke(app, ["extract", "divipola"])
    assert result.exit_code == 1 and result.stdout == ""


def test_does_not_fall_back_to_admin(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("PITS_S3_WRITER_ACCESS_KEY_ID", "PITS_S3_WRITER_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name)
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "ADMINKEYEXAMPLE0001")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", S3_SECRET)
    result = runner.invoke(app, ["extract", "divipola"])
    assert result.exit_code == 1 and result.stdout == ""
    assert "PITS_S3_WRITER_ACCESS_KEY_ID" in result.stderr
    assert S3_SECRET not in result.stdout + result.stderr

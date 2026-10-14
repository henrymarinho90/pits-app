"""Offline tests for `pits extract brand-fleet` (store and SODA replaced through the CLI seams)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from brand_fleet_support import (
    B1,
    B2,
    BOYACA,
    RISARALDA,
    FakeBrandFleet,
    boyaca_row,
    columns,
    risaralda_row,
)
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
PREFIX = "gobernacion_boyaca_parque_automotor/extraction_date=2026-10-14"


class World:
    def __init__(self) -> None:
        self.fake = FakeBrandFleet(BOYACA, [boyaca_row(i) for i in range(4)])
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
    monkeypatch.setattr(extract_cli, "clock", lambda: datetime(2026, 10, 14, 12, tzinfo=UTC))
    monkeypatch.setattr(extract_cli, "batch_id_factory", lambda: w.batch_ids.pop(0))
    return w


def manifest_path(batch_id: str) -> str:
    return f"{PREFIX}/batch_id={batch_id}/manifest.json"


def invoke(*extra: str, source: str = "boyaca"):
    return runner.invoke(app, ["extract", "brand-fleet", "--source", source, *extra])


def test_commits_with_exact_output(world: World) -> None:
    result = invoke()
    assert result.exit_code == 0, result.stderr
    assert result.stdout == (
        f"outcome=committed source=boyaca batch_id={B1} rows_updated=2026-07-06 rows=4 files=1 "
        f"manifest=s3://pits-raw/{manifest_path(B1)}\n"
    )
    assert result.stderr == ""
    manifest = Manifest.from_json(world.store.get(manifest_path(B1)))
    assert manifest.app_token_used is True and manifest.watermark.column == "rowsUpdatedAt"


def test_risaralda_source(world: World) -> None:
    world.fake = FakeBrandFleet(RISARALDA, [risaralda_row(i) for i in range(2)])
    result = invoke(source="risaralda")
    assert result.exit_code == 0, result.stderr
    assert "source=risaralda " in result.stdout
    assert "gobernacion_risaralda_parque_automotor/" in result.stdout
    assert all("placa" not in str(p) for p in world.fake.requests)


def test_source_is_required_and_validated(world: World) -> None:
    missing = runner.invoke(app, ["extract", "brand-fleet"])
    assert missing.exit_code == 2 and world.store.objects == {}
    unknown = invoke(source="narino")
    assert unknown.exit_code == 2 and world.store.objects == {}


def test_second_run_is_unchanged_and_force_creates_batch(world: World) -> None:
    assert invoke().exit_code == 0
    before = set(world.store.objects)
    second = invoke()
    assert second.exit_code == 0, second.stderr
    assert second.stdout.startswith(f"outcome=unchanged source=boyaca batch_id={B1} ")
    assert set(world.store.objects) == before
    forced = invoke("--force")
    assert forced.exit_code == 0, forced.stderr
    assert forced.stdout.startswith(f"outcome=committed source=boyaca batch_id={B2} ")


def test_schema_drift_exit_1(world: World) -> None:
    world.fake.columns = columns(BOYACA)[:-1]
    result = invoke()
    assert result.exit_code == 1
    assert result.stdout == "" and result.stderr.startswith("error: ")
    assert world.store.objects == {}
    assert TOKEN not in result.stdout + result.stderr


def test_row_with_plate_exit_1_without_writes(world: World) -> None:
    data = [risaralda_row(i) for i in range(3)]
    data[0] = {**data[0], "placa": "AAA000"}
    world.fake = FakeBrandFleet(RISARALDA, data, honour_select=False)
    result = invoke(source="risaralda")
    assert result.exit_code == 1 and "placa" in result.stderr
    assert "AAA000" not in result.stdout + result.stderr
    assert world.store.objects == {}


def test_truncation_exit_3(world: World) -> None:
    world.fake.total_override = 9
    result = invoke()
    assert result.exit_code == 3 and "Truncated" in result.stderr
    assert TOKEN not in result.stdout + result.stderr


def test_http_503_exit_3(world: World) -> None:
    world.fake.status = 503
    result = invoke()
    assert result.exit_code == 3 and result.stdout == ""
    assert TOKEN not in result.stdout + result.stderr


def test_invalid_storage_config_exit_1(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("S3_RAW_BUCKET", raising=False)
    monkeypatch.setenv("S3_NORMALIZED_BUCKET", "pits-raw")
    result = invoke()
    assert result.exit_code == 1 and result.stdout == ""


def test_does_not_fall_back_to_admin(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("PITS_S3_WRITER_ACCESS_KEY_ID", "PITS_S3_WRITER_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name)
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "ADMINKEYEXAMPLE0001")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", S3_SECRET)
    result = invoke()
    assert result.exit_code == 1 and result.stdout == ""
    assert "PITS_S3_WRITER_ACCESS_KEY_ID" in result.stderr
    assert S3_SECRET not in result.stdout + result.stderr

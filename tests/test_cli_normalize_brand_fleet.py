"""Offline tests for `pits normalize brand-fleet` (Stubber client for bucket checks)."""

from __future__ import annotations

import json
import re
from datetime import date

import pytest
from botocore.stub import Stubber
from brand_fleet_support import B1, BOYACA, RISARALDA, boyaca_row, put_brand_batch, risaralda_row
from typer.testing import CliRunner

from pits.cli import app
from pits.ingestion.manifest import manifest_key
from pits.ingestion.raw_store import MemoryRawStore, RawStoreTransientError, batch_prefix
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
    r"outcome=(created|already_present) source=boyaca rows_updated=2026-07-06 "
    r"fingerprint=([0-9a-f]{64}) batch=" + B1 + r" rows=2 vehicles=3 "
    r"manifest=s3://pits-norm/regional_fleet_brand/"
    r"source_system=gobernacion_boyaca_parque_automotor/rows_updated=2026-07-06/"
    r"fingerprint=\2/manifest\.json\n"
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
        result = runner.invoke(app, ["normalize", "brand-fleet", *args])
        stubber.assert_no_pending_responses()
    return result


def boyaca_rows() -> list[dict[str, str]]:
    return [boyaca_row(0), boyaca_row(3), boyaca_row(2, linea="OTRA")]


def test_success_exact_stdout_then_already_present(world: World) -> None:
    put_brand_batch(world.raw, BOYACA, B1, date(2026, 10, 14), boyaca_rows())
    first = run(world, "--source", "boyaca")
    assert first.exit_code == 0, first.stderr
    m = LINE.fullmatch(first.stdout)
    assert m and m.group(1) == "created" and first.stderr == ""
    second = run(world, "--source", "boyaca")
    assert second.exit_code == 0 and second.stderr == ""
    assert second.stdout == first.stdout.replace("outcome=created", "outcome=already_present")
    assert len(world.norm.objects) == 2  # csv + manifest


def test_source_is_required(world: World) -> None:
    result = runner.invoke(app, ["normalize", "brand-fleet"])
    assert result.exit_code == 2 and result.stdout == ""
    result = runner.invoke(app, ["normalize", "brand-fleet", "--source", "narino"])
    assert result.exit_code == 2 and result.stdout == ""


def test_raw_batch_with_other_schema_exits_1(world: World) -> None:
    day = date(2026, 10, 14)
    put_brand_batch(world.raw, RISARALDA, B1, day, [risaralda_row(0)])
    key = manifest_key(batch_prefix(RISARALDA.source_system, day, B1))
    data = json.loads(world.raw.get(key))
    # the batch re-declared with the full source schema (including the plate column)
    data["schema"] = [{"name": c.name, "data_type": c.data_type} for c in RISARALDA.source_schema]
    world.raw.objects[key] = json.dumps(data, indent=2, sort_keys=True).encode()
    result = run(world, "--source", "risaralda")
    assert result.exit_code == 1 and result.stdout == ""
    assert "schema other than the requested" in result.stderr
    assert world.norm.objects == {}


def test_invalid_value_exits_1_without_leaking_data(world: World) -> None:
    put_brand_batch(
        world.raw, BOYACA, B1, date(2026, 10, 14), [*boyaca_rows(), boyaca_row(9, marca="")]
    )
    result = run(world, "--source", "boyaca")
    assert result.exit_code == 1 and result.stdout == ""
    assert result.stderr.startswith("error: ") and "Traceback" not in result.stderr
    assert world.norm.objects == {}


def test_without_raw_batches_exits_1(world: World) -> None:
    result = run(world, "--source", "boyaca")
    assert result.exit_code == 1 and result.stdout == ""
    assert "No committed raw batch" in result.stderr


def test_transient_error_exits_3(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(prefix: str) -> list[str]:
        raise RawStoreTransientError("simulated network failure")

    monkeypatch.setattr(world.raw, "list_prefixes", boom)
    result = run(world, "--source", "boyaca")
    assert result.exit_code == 3
    assert result.stdout == "" and result.stderr == "error: simulated network failure\n"


def test_does_not_fall_back_to_admin(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("PITS_S3_WRITER_ACCESS_KEY_ID", "PITS_S3_WRITER_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name)
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "ADMINKEYEXAMPLE0001")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", SECRET)
    result = runner.invoke(app, ["normalize", "brand-fleet", "--source", "boyaca"])
    assert result.exit_code == 1 and result.stdout == ""
    assert "PITS_S3_WRITER_ACCESS_KEY_ID" in result.stderr

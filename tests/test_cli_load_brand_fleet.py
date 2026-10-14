"""Offline tests for `pits load brand-fleet` (D138); the load itself is replaced by a fake."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import pytest
from typer.testing import CliRunner

from pits.cli import app
from pits.warehouse import load_cli
from pits.warehouse.brand_fleet_load import BrandFleetLoadResult
from pits.warehouse.errors import WarehousePermanentError, WarehouseTransientError
from pits.warehouse.fx_rate_load import Outcome

runner = CliRunner()
SENTINEL = "sentinel-load-pw-0123456789"
S3_SECRET = "s3-secret-sentinel-0123456789-abcdef"
FP = "a" * 64
SYSTEM = "gobernacion_boyaca_parque_automotor"
KEY = f"regional_fleet_brand/source_system={SYSTEM}/rows_updated=2024-08-30/fingerprint={FP}/m"


def brand_result(outcome=Outcome.LOADED):
    return BrandFleetLoadResult(outcome, SYSTEM, date(2024, 8, 30), 5, FP, 30, 182379, 30, 12, KEY)


@pytest.fixture
def env(monkeypatch):
    values = {
        "S3_ENDPOINT_URL": "http://127.0.0.1:1",
        "PITS_S3_READER_ACCESS_KEY_ID": "READERKEYEXAMPLE0001",
        "PITS_S3_READER_SECRET_ACCESS_KEY": S3_SECRET,
        "S3_RAW_BUCKET": "pits-raw",
        "PITS_PG_LOADER_PASSWORD": SENTINEL,
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(load_cli, "client_factory", lambda s: object())
    monkeypatch.setattr(load_cli, "store_factory", lambda c, b: object())

    @contextmanager
    def fake_warehouse(settings):
        yield object()

    monkeypatch.setattr(load_cli, "brand_fleet_warehouse_factory", fake_warehouse)
    monkeypatch.setattr(load_cli, "settings_factory", lambda e: object())


def patch_load(monkeypatch, fn):
    monkeypatch.setattr(load_cli, "load_brand_fleet", fn)


def invoke(*args: str, source: str = "boyaca"):
    return runner.invoke(app, ["load", "brand-fleet", "--source", source, *args])


def test_help_lists_brand_fleet():
    assert "brand-fleet" in runner.invoke(app, ["load", "--help"]).output


def test_success_output_and_arguments(env, monkeypatch):
    seen = {}

    def fake(store, warehouse, raw_bucket, source, **kwargs):
        seen.update(raw_bucket=raw_bucket, source=source, **kwargs)
        return brand_result()

    patch_load(monkeypatch, fake)
    out = invoke("--fingerprint", FP, "--repair")
    assert out.exit_code == 0, out.output
    assert out.output.strip() == (
        f"outcome=loaded source=boyaca rows_updated=2024-08-30 load_id=5 fingerprint={FP} "
        f"rows=30 vehicles=182379 inserted=30 deleted=12 manifest=s3://pits-normalized/{KEY}"
    )
    assert seen["raw_bucket"] == "pits-raw" and seen["fingerprint"] == FP and seen["repair"]
    assert seen["source"].source_system == SYSTEM


def test_risaralda_source_is_passed_to_the_loader(env, monkeypatch):
    seen = {}

    def fake(store, warehouse, raw_bucket, source, **kwargs):
        seen["source"] = source
        return brand_result()

    patch_load(monkeypatch, fake)
    assert invoke(source="risaralda").exit_code == 0
    assert seen["source"].key == "risaralda"


def test_already_loaded_exit_0(env, monkeypatch):
    patch_load(monkeypatch, lambda *a, **k: brand_result(Outcome.ALREADY_LOADED))
    out = invoke()
    assert out.exit_code == 0 and "outcome=already_loaded" in out.output


@pytest.mark.parametrize(
    "args",
    [
        ["--fingerprint", "A" * 64],
        ["--fingerprint", "a" * 63],
        ["--nope"],
        ["--source", "narino"],
    ],
)
def test_bad_arguments_are_usage_errors_before_anything_runs(monkeypatch, args):
    patch_load(monkeypatch, lambda *a, **k: pytest.fail("must not run"))
    assert runner.invoke(app, ["load", "brand-fleet", "--source", "boyaca", *args]).exit_code == 2


def test_source_is_required(monkeypatch):
    patch_load(monkeypatch, lambda *a, **k: pytest.fail("must not run"))
    assert runner.invoke(app, ["load", "brand-fleet"]).exit_code == 2


@pytest.mark.parametrize(
    ("exc", "code"),
    [(WarehouseTransientError("lock busy"), 3), (WarehousePermanentError("drift"), 1)],
)
def test_error_exit_codes(env, monkeypatch, exc, code):
    def boom(*a, **k):
        raise exc

    patch_load(monkeypatch, boom)
    out = invoke()
    assert out.exit_code == code and str(exc) in out.output
    assert SENTINEL not in out.output


def test_connection_failure_is_transient(env, monkeypatch):
    @contextmanager
    def refused(settings):
        raise WarehouseTransientError("connect as loader: OperationalError")
        yield

    monkeypatch.setattr(load_cli, "brand_fleet_warehouse_factory", refused)
    out = invoke()
    assert out.exit_code == 3 and SENTINEL not in out.output


def test_missing_configuration_exits_1(env, monkeypatch):
    monkeypatch.delenv("PITS_PG_LOADER_PASSWORD")
    monkeypatch.setattr(load_cli, "settings_factory", lambda e: load_cli._default_settings(e))
    out = invoke()
    assert out.exit_code == 1 and "PITS_PG_LOADER_PASSWORD" in out.output


def test_does_not_fall_back_to_admin(env, monkeypatch):
    for name in ("PITS_S3_READER_ACCESS_KEY_ID", "PITS_S3_READER_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name)
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "ADMINKEYEXAMPLE0001")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", S3_SECRET)
    out = invoke()
    assert out.exit_code == 1 and "PITS_S3_READER_ACCESS_KEY_ID" in out.output
    assert S3_SECRET not in out.output

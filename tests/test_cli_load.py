from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import pytest
from typer.testing import CliRunner

from pits.cli import app
from pits.warehouse import load_cli
from pits.warehouse.errors import (
    WarehouseConfigError,
    WarehousePermanentError,
    WarehouseTransientError,
)
from pits.warehouse.fx_rate_load import LoadResult, Outcome
from pits.warehouse.settings import WarehouseSettings

runner = CliRunner()
SENTINEL = "sentinel-load-pw-0123456789"
FP = "a" * 64


def result(outcome=Outcome.LOADED):
    return LoadResult(
        outcome, 5, FP, 100, 100, 0, 0, date(1991, 12, 2), date(2026, 10, 13), "fx_rate/m.json"
    )


@pytest.fixture
def env(monkeypatch):
    values = {
        "S3_ENDPOINT_URL": "http://127.0.0.1:1",
        "S3_ACCESS_KEY_ID": "ak",
        "S3_SECRET_ACCESS_KEY": "s3-secret-sentinel-0123456789",
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

    monkeypatch.setattr(load_cli, "warehouse_factory", fake_warehouse)


def patch_load(monkeypatch, fn):
    monkeypatch.setattr(load_cli, "load_fx_rate", fn)


def test_help_lists_fx_rate():
    out = runner.invoke(app, ["load", "--help"]).output
    assert "fx-rate" in out


def test_success_output_and_arguments(env, monkeypatch):
    seen = {}

    def fake(store, warehouse, raw_bucket, **kwargs):
        seen.update(raw_bucket=raw_bucket, **kwargs)
        return result()

    patch_load(monkeypatch, fake)
    out = runner.invoke(app, ["load", "fx-rate", "--fingerprint", FP, "--repair"])
    assert out.exit_code == 0
    assert out.output.strip() == (
        f"outcome=loaded load_id=5 fingerprint={FP} rows=100 inserted=100 updated=0 deleted=0 "
        "coverage=1991-12-02..2026-10-13 manifest=s3://pits-normalized/fx_rate/m.json"
    )
    assert seen["raw_bucket"] == "pits-raw" and seen["fingerprint"] == FP and seen["repair"]


def test_already_loaded_exit_0(env, monkeypatch):
    patch_load(monkeypatch, lambda *a, **k: result(Outcome.ALREADY_LOADED))
    out = runner.invoke(app, ["load", "fx-rate"])
    assert out.exit_code == 0 and "outcome=already_loaded" in out.output


@pytest.mark.parametrize("bad", ["abc", "A" * 64, "g" * 64, "a" * 63])
def test_bad_fingerprint_is_usage_error_before_anything_runs(monkeypatch, bad):
    monkeypatch.setattr(load_cli, "load_fx_rate", lambda *a, **k: pytest.fail("must not run"))
    out = runner.invoke(app, ["load", "fx-rate", "--fingerprint", bad])
    assert out.exit_code == 2


def test_unknown_option_is_usage_error():
    assert runner.invoke(app, ["load", "fx-rate", "--nope"]).exit_code == 2


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (WarehouseTransientError("lock busy"), 3),
        (WarehousePermanentError("drift"), 1),
    ],
)
def test_error_exit_codes(env, monkeypatch, exc, code):
    def boom(*a, **k):
        raise exc

    patch_load(monkeypatch, boom)
    out = runner.invoke(app, ["load", "fx-rate"])
    assert out.exit_code == code and str(exc) in out.output
    assert SENTINEL not in out.output


def test_connection_failures_map_through_the_warehouse_factory(env, monkeypatch):
    @contextmanager
    def refused(settings):
        raise WarehouseTransientError("connect as loader: OperationalError")
        yield

    monkeypatch.setattr(load_cli, "warehouse_factory", refused)
    out = runner.invoke(app, ["load", "fx-rate"])
    assert out.exit_code == 3 and SENTINEL not in out.output


def test_missing_loader_password_exits_1(env, monkeypatch):
    monkeypatch.delenv("PITS_PG_LOADER_PASSWORD")
    monkeypatch.setattr(
        load_cli,
        "settings_factory",
        lambda e: load_cli._default_settings(e),
    )
    out = runner.invoke(app, ["load", "fx-rate"])
    assert out.exit_code == 1 and "PITS_PG_LOADER_PASSWORD" in out.output


def test_missing_s3_config_exits_1(env, monkeypatch):
    monkeypatch.delenv("S3_RAW_BUCKET")
    out = runner.invoke(app, ["load", "fx-rate"])
    assert out.exit_code == 1 and "S3_RAW_BUCKET" in out.output


def test_admin_credentials_are_not_required(env, monkeypatch):
    for name in ("POSTGRES_USER", "POSTGRES_PASSWORD", "PITS_PG_READER_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    patch_load(monkeypatch, lambda *a, **k: result())
    assert runner.invoke(app, ["load", "fx-rate"]).exit_code == 0


def test_config_error_message_has_no_secret(env, monkeypatch):
    def bad_settings(e):
        raise WarehouseConfigError("PITS_PG_HOST must be a loopback host")

    monkeypatch.setattr(load_cli, "settings_factory", bad_settings)
    out = runner.invoke(app, ["load", "fx-rate"])
    assert out.exit_code == 1 and SENTINEL not in out.output


def test_default_settings_use_the_loader_profile_only(monkeypatch):
    settings = load_cli._default_settings({"PITS_PG_LOADER_PASSWORD": SENTINEL})
    assert isinstance(settings, WarehouseSettings)
    assert SENTINEL not in repr(settings)

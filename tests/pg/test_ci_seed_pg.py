"""scripts/ci_seed_warehouse.py (D113) against per-test databases: seed, dbt build, verify."""

from __future__ import annotations

import importlib.util
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pits.cli import app as pits_app
from pits.transform import cli as tcli
from pits.transform import runner as rn
from pits.warehouse.connection import connect
from pits.warehouse.migrate import run_migrate
from pits.warehouse.settings import Profile

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci_seed_warehouse.py"
runner = CliRunner()


@pytest.fixture
def seeder(pg_settings, monkeypatch):
    spec = importlib.util.spec_from_file_location("ci_seed_warehouse", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "settings_factory", lambda profile: pg_settings)
    run_migrate(pg_settings)
    return module


@pytest.fixture
def build(pg_settings, monkeypatch, tmp_path):
    project = tmp_path / "transform"
    shutil.copytree(
        rn.default_project_dir(),
        project,
        ignore=shutil.ignore_patterns("target", "logs", "dbt_packages"),
    )
    monkeypatch.setattr(tcli, "project_dir_factory", lambda: project)
    monkeypatch.setattr(tcli, "settings_factory", lambda env: pg_settings)
    return lambda: runner.invoke(pits_app, ["transform", "build"])


def _run(module, command):
    return runner.invoke(module.app, [command])


def test_seed_build_verify_and_second_seed_is_refused(seeder, build, pg_settings, capfd):
    result = _run(seeder, "seed")
    assert result.exit_code == 0, result.output
    built = build()
    assert built.exit_code == 0, built.output + capfd.readouterr().out
    result = _run(seeder, "verify")
    assert result.exit_code == 0, result.output
    assert pg_settings.loader_password not in result.output

    again = _run(seeder, "seed")
    assert again.exit_code == 1
    assert "not empty" in again.output
    admin = connect(pg_settings, Profile.ADMIN, autocommit=True)
    try:
        count = admin.execute("SELECT count(*) FROM ops.load_run").fetchone()[0]
    finally:
        admin.close()
    assert count == 2  # the refused seed wrote nothing
    assert build().exit_code == 0  # idempotent
    assert _run(seeder, "verify").exit_code == 0


def test_verify_detects_a_mismatch(seeder, build, monkeypatch):
    assert _run(seeder, "seed").exit_code == 0
    assert build().exit_code == 0
    monkeypatch.setattr(seeder, "FX_RATES", [*seeder.FX_RATES[:-1], Decimal("1")])
    result = _run(seeder, "verify")
    assert result.exit_code == 1
    assert "fct_fx_rate_daily" in result.output


def test_failed_seed_rolls_everything_back(seeder, pg_settings, monkeypatch):
    # The bad row fails AFTER the fx rows and both load_runs were inserted.
    bad = ("BOGOTA, D.C.", "BOGOTA, D.C.", "OTROS", "ACTIVO", "MALA", 2018, 0)
    monkeypatch.setattr(seeder, "FLEET", [*seeder.FLEET, bad])
    result = _run(seeder, "seed")
    assert result.exit_code != 0
    assert result.output.startswith("error:") or "error:" in result.output
    assert "Traceback" not in result.output
    admin = connect(pg_settings, Profile.ADMIN, autocommit=True)
    try:
        counts = [
            admin.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ("ops.load_run", "landing.fx_rate", "landing.vehicle_fleet_snapshot")
        ]
    finally:
        admin.close()
    assert counts == [0, 0, 0]


def test_verify_detects_a_fleet_mismatch(seeder, build, monkeypatch):
    assert _run(seeder, "seed").exit_code == 0
    assert build().exit_code == 0
    monkeypatch.setattr(seeder, "FLEET", seeder.FLEET[:-1])
    result = _run(seeder, "verify")
    assert result.exit_code == 1
    assert "fct_vehicle_fleet_snapshot" in result.output


def test_verify_detects_a_normalization_regression(seeder, build, monkeypatch):
    assert _run(seeder, "seed").exit_code == 0
    assert build().exit_code == 0
    monkeypatch.setattr(
        seeder, "FLEET_NORM_KEYS", [("NARIÑO", "PASTO", "CAMION"), *seeder.FLEET_NORM_KEYS[:2]]
    )
    result = _run(seeder, "verify")
    assert result.exit_code == 1
    assert "normalized keys" in result.output

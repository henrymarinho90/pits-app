"""Offline tests of `pits db init-airflow-meta` (D93): config, output and exit codes."""

import pytest
from typer.testing import CliRunner

from pits.cli import app
from pits.warehouse import airflow_meta as am
from pits.warehouse import cli as db_cli
from pits.warehouse.errors import (
    WarehouseConfigError,
    WarehousePermanentError,
    WarehouseTransientError,
)
from pits.warehouse.settings import Profile

runner = CliRunner()
ADMIN_PW = "sentinel-admin-pw-0123456789"
META_PW = "sentinel-airflow-meta-pw-0123456789"


@pytest.fixture
def env(monkeypatch):
    for name in ("PITS_PG_HOST", "POSTGRES_HOST_PORT", "PITS_WAREHOUSE_DB"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("POSTGRES_USER", "pits")
    monkeypatch.setenv("POSTGRES_PASSWORD", ADMIN_PW)
    monkeypatch.setenv(am.PASSWORD_ENV, META_PW)


def _stub(monkeypatch, created, calls=None):
    def fake(settings, password):
        if calls is not None:
            calls.append((settings, password))
        return am.AirflowMetaResult("airflow_meta", "airflow_meta", created)

    monkeypatch.setattr(db_cli, "init_airflow_meta", fake)


def test_help_lists_command():
    result = runner.invoke(app, ["db", "--help"])
    assert result.exit_code == 0
    assert "init-airflow-meta" in result.output


@pytest.mark.parametrize(("created", "status"), [(True, "created"), (False, "unchanged")])
def test_success_output(env, monkeypatch, created, status):
    calls = []
    _stub(monkeypatch, created, calls)
    result = runner.invoke(app, ["db", "init-airflow-meta"])
    assert result.exit_code == 0
    assert f"database=airflow_meta role=airflow_meta status={status}" in result.output
    assert ADMIN_PW not in result.output and META_PW not in result.output
    assert calls[0][1] == META_PW
    assert calls[0][0].credentials(Profile.ADMIN)[0] == "pits"


@pytest.mark.parametrize("value", [None, "", "short-pw", " " + META_PW, META_PW + "\n"])
def test_bad_password_exits_1(env, monkeypatch, value):
    _stub(monkeypatch, True)
    if value is None:
        monkeypatch.delenv(am.PASSWORD_ENV)
    else:
        monkeypatch.setenv(am.PASSWORD_ENV, value)
    result = runner.invoke(app, ["db", "init-airflow-meta"])
    assert result.exit_code == 1
    assert am.PASSWORD_ENV in result.output
    assert META_PW not in result.output


def test_missing_admin_exits_1(env, monkeypatch):
    _stub(monkeypatch, True)
    monkeypatch.delenv("POSTGRES_PASSWORD")
    result = runner.invoke(app, ["db", "init-airflow-meta"])
    assert result.exit_code == 1
    assert "POSTGRES_PASSWORD" in result.output


def test_unexpected_argument_exits_2(env):
    assert runner.invoke(app, ["db", "init-airflow-meta", "extra"]).exit_code == 2


@pytest.mark.parametrize(
    ("exc", "code"),
    [(WarehouseTransientError("lock busy"), 3), (WarehousePermanentError("bad"), 1)],
)
def test_error_exit_codes(env, monkeypatch, exc, code):
    def boom(settings, password):
        raise exc

    monkeypatch.setattr(db_cli, "init_airflow_meta", boom)
    result = runner.invoke(app, ["db", "init-airflow-meta"])
    assert result.exit_code == code
    assert META_PW not in result.output and ADMIN_PW not in result.output


@pytest.mark.parametrize("name", ["Airflow", "1meta", "a-b", "x" * 64, ""])
def test_invalid_names_rejected_before_connecting(monkeypatch, name):
    def boom(settings):
        raise AssertionError("must not connect")

    monkeypatch.setattr(am, "run_lock", boom)
    with pytest.raises(WarehouseConfigError):
        am.init_airflow_meta(None, META_PW, dbname=name)
    with pytest.raises(WarehouseConfigError):
        am.init_airflow_meta(None, META_PW, role=name)

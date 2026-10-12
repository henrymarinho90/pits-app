import pytest
from typer.testing import CliRunner

from pits.cli import app
from pits.warehouse import cli as db_cli
from pits.warehouse.errors import WarehousePermanentError, WarehouseTransientError
from pits.warehouse.migrate import MigrateResult

runner = CliRunner()
SENTINEL = "sentinel-db-pw-0123456789"


@pytest.fixture
def env(monkeypatch):
    for name in ("PITS_PG_HOST", "POSTGRES_HOST_PORT", "PITS_WAREHOUSE_DB"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("POSTGRES_USER", "pits")
    monkeypatch.setenv("POSTGRES_PASSWORD", SENTINEL)
    monkeypatch.setenv("PITS_PG_LOADER_PASSWORD", SENTINEL + "-l")
    monkeypatch.setenv("PITS_PG_READER_PASSWORD", SENTINEL + "-r")
    monkeypatch.setenv("PITS_PG_TRANSFORMER_PASSWORD", SENTINEL + "-t")


def test_help_lists_migrate():
    result = runner.invoke(app, ["db", "--help"])
    assert result.exit_code == 0
    assert "migrate" in result.output


def test_success_output(env, monkeypatch):
    monkeypatch.setattr(db_cli, "run_migrate", lambda settings: MigrateResult(2, 1))
    result = runner.invoke(app, ["db", "migrate"])
    assert result.exit_code == 0
    assert "applied=2 skipped=1" in result.output
    assert SENTINEL not in result.output


def test_missing_config_exits_1(monkeypatch):
    monkeypatch.delenv("PITS_PG_LOADER_PASSWORD", raising=False)
    monkeypatch.setenv("POSTGRES_USER", "pits")
    monkeypatch.setenv("POSTGRES_PASSWORD", SENTINEL)
    result = runner.invoke(app, ["db", "migrate"])
    assert result.exit_code == 1
    assert "PITS_PG_LOADER_PASSWORD" in result.output


@pytest.mark.parametrize(
    ("exc", "code"),
    [(WarehouseTransientError("lock busy"), 3), (WarehousePermanentError("bad"), 1)],
)
def test_error_exit_codes(env, monkeypatch, exc, code):
    def boom(settings):
        raise exc

    monkeypatch.setattr(db_cli, "run_migrate", boom)
    result = runner.invoke(app, ["db", "migrate"])
    assert result.exit_code == code
    assert SENTINEL not in result.output


def test_unknown_option_is_usage_error(env):
    assert runner.invoke(app, ["db", "migrate", "--nope"]).exit_code == 2

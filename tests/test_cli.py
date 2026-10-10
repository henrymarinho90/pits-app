import importlib
from importlib.metadata import PackageNotFoundError, entry_points

import pytest
from typer.testing import CliRunner

import pits
from pits.cli import app

runner = CliRunner()


def test_help_lists_version_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "version" in result.output


def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 2
    assert "version" in result.output


def test_unknown_command_fails() -> None:
    result = runner.invoke(app, ["nope"])
    assert result.exit_code != 0


def test_version_command_prints_package_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.output.strip() == pits.__version__


def test_version_is_stable_across_runs() -> None:
    first = runner.invoke(app, ["version"])
    second = runner.invoke(app, ["version"])
    assert first.output == second.output


def test_version_fallback_when_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_not_found(name: str) -> str:
        raise PackageNotFoundError(name)

    try:
        monkeypatch.setattr(importlib.metadata, "version", raise_not_found)
        importlib.reload(pits)
        assert pits.__version__ == "0.0.0"
    finally:
        monkeypatch.undo()
        importlib.reload(pits)


def test_console_script_entry_point_is_registered() -> None:
    scripts = entry_points(group="console_scripts")
    (ep,) = [ep for ep in scripts if ep.name == "pits"]
    assert ep.value == "pits.cli:app"
    assert ep.load() is app

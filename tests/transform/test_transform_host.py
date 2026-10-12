"""`pits transform` host preflight (D91): `postgres`/5432 allowed, other hosts fail early."""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from typer.testing import CliRunner

from pits.cli import app
from pits.transform import cli as tcli

SENTINEL = "sentinel-transform-pw-0123456789"
DBT = "/venv/bin/dbt"
runner = CliRunner()


class FakeDbt:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, env):
        self.calls.append((list(argv), dict(env)))
        return 0


@pytest.fixture
def cli_env(monkeypatch, tmp_path):
    (tmp_path / "dbt_project.yml").write_text("name: x\n")
    environ = {"PATH": "/bin", "PITS_PG_TRANSFORMER_PASSWORD": SENTINEL}
    fake = FakeDbt()
    sessions = []

    @contextmanager
    def session(settings):
        sessions.append(settings)
        yield object()

    monkeypatch.setattr(tcli, "environ_factory", lambda: environ)
    monkeypatch.setattr(tcli, "project_dir_factory", lambda: tmp_path)
    monkeypatch.setattr(tcli, "executable_factory", lambda: DBT)
    monkeypatch.setattr(tcli, "dbt_runner", fake)
    monkeypatch.setattr(tcli, "session_factory", session)
    return environ, fake, sessions


def test_build_with_compose_host_and_port_5432(cli_env):
    environ, fake, _ = cli_env
    environ["PITS_PG_HOST"] = "postgres"
    environ["POSTGRES_HOST_PORT"] = "5432"
    assert runner.invoke(app, ["transform", "build"]).exit_code == 0
    child = fake.calls[0][1]
    assert child["PITS_PG_HOST"] == "postgres"
    assert child["POSTGRES_HOST_PORT"] == "5432"


@pytest.mark.parametrize("host", ["POSTGRES", "postgres.example.com"])
def test_build_with_disallowed_host_fails_before_dbt(cli_env, host):
    environ, fake, sessions = cli_env
    environ["PITS_PG_HOST"] = host
    result = runner.invoke(app, ["transform", "build"])
    assert result.exit_code == 1
    assert "PITS_PG_HOST" in result.output
    assert host not in result.output and SENTINEL not in result.output
    assert fake.calls == [] and sessions == []

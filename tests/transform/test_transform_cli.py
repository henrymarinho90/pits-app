from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pits.cli import app
from pits.transform import cli as tcli
from pits.transform import runner as rn
from pits.warehouse.errors import WarehousePermanentError, WarehouseTransientError

runner = CliRunner()
SENTINEL = "sentinel-transform-pw-0123456789"
DBT = "/venv/bin/dbt"


class FakeDbt:
    def __init__(self, code=0):
        self.code = code
        self.calls = []

    def __call__(self, argv, env):
        self.calls.append((list(argv), dict(env)))
        print("dbt-output-line")
        return self.code


@pytest.fixture
def project(tmp_path):
    (tmp_path / "dbt_project.yml").write_text("name: x\n")
    return tmp_path


@pytest.fixture
def env(monkeypatch, project):
    environ = {
        "PATH": "/bin",
        "PITS_PG_TRANSFORMER_PASSWORD": SENTINEL,
        "PITS_PG_LOADER_PASSWORD": "loader-pw-0123456789abc",
        "POSTGRES_PASSWORD": "admin-pw",
        "POSTGRES_HOST_PORT": "5444",
        "PITS_WAREHOUSE_DB": "wh_test",
        "PGPASSWORD": "pgpass-sentinel",
        "PGSERVICE": "x",
        "DBT_ENGINE_HINTS_ENABLED": "1",
        "DBT_TARGET": "prod",
        "KEEP_ME": "yes",
    }
    monkeypatch.setattr(tcli, "environ_factory", lambda: environ)
    monkeypatch.setattr(tcli, "project_dir_factory", lambda: project)
    monkeypatch.setattr(tcli, "executable_factory", lambda: DBT)
    fake = FakeDbt()
    monkeypatch.setattr(tcli, "dbt_runner", fake)
    sessions = []

    @contextmanager
    def session(settings):
        sessions.append(settings)
        yield object()

    monkeypatch.setattr(tcli, "session_factory", session)
    return environ, fake, sessions


def invoke(*args):
    return runner.invoke(app, ["transform", *args])


@pytest.mark.parametrize(
    ("command", "sub"),
    [("parse", ["parse"]), ("build", ["build"]), ("freshness", ["source", "freshness"])],
)
def test_argv(env, project, command, sub):
    _, fake, _ = env
    assert invoke(command).exit_code == 0
    ((argv, _),) = fake.calls
    assert argv == [DBT, *sub, "--project-dir", str(project), "--profiles-dir", str(project)]


def test_dbt_output_passes_through(env):
    assert "dbt-output-line" in invoke("build").output


def test_child_env_for_build(env):
    environ, fake, _ = env
    assert invoke("build").exit_code == 0
    child = fake.calls[0][1]
    assert not [k for k in child if k.startswith(("PG", "DBT_ENGINE_"))]
    assert "DBT_TARGET" not in child and "POSTGRES_PASSWORD" not in child
    assert "PITS_PG_LOADER_PASSWORD" not in child
    assert child["DO_NOT_TRACK"] == "1"
    assert child["DBT_SEND_ANONYMOUS_USAGE_STATS"] == "False"
    assert child["PITS_PG_TRANSFORMER_USER"] == "pits_transformer"
    assert child["PITS_PG_TRANSFORMER_PASSWORD"] == SENTINEL
    assert child["PITS_WAREHOUSE_DB"] == "wh_test"
    assert child["POSTGRES_HOST_PORT"] == "5444"
    assert child["KEEP_ME"] == "yes" and child["PATH"] == "/bin"
    assert "PGPASSWORD" in environ  # the parent environment is not mutated


def test_parse_needs_no_password_nor_session(env):
    environ, fake, sessions = env
    del environ["PITS_PG_TRANSFORMER_PASSWORD"]
    result = invoke("parse")
    assert result.exit_code == 0
    assert sessions == []
    child = fake.calls[0][1]
    assert "PITS_PG_TRANSFORMER_PASSWORD" not in child and "PGPASSWORD" not in child
    assert child["DO_NOT_TRACK"] == "1"


@pytest.mark.parametrize("command", ["build", "freshness"])
def test_missing_password_exits_1_without_running_dbt(env, command):
    environ, fake, sessions = env
    del environ["PITS_PG_TRANSFORMER_PASSWORD"]
    result = invoke(command)
    assert result.exit_code == 1
    assert "PITS_PG_TRANSFORMER_PASSWORD" in result.output
    assert fake.calls == [] and sessions == []


@pytest.mark.parametrize("command", ["parse", "build", "freshness"])
def test_missing_project_exits_1(env, monkeypatch, tmp_path, command):
    monkeypatch.setattr(tcli, "project_dir_factory", lambda: tmp_path / "nowhere")
    result = invoke(command)
    assert result.exit_code == 1
    assert "dbt_project.yml" in result.output
    assert env[1].calls == []


@pytest.mark.parametrize(("dbt_code", "expected"), [(0, 0), (1, 1), (2, 1), (137, 1)])
def test_exit_code_mapping(env, dbt_code, expected):
    env[1].code = dbt_code
    assert invoke("build").exit_code == expected


@pytest.mark.parametrize(
    "error", [WarehouseTransientError("busy"), WarehousePermanentError("auth")]
)
def test_session_errors_map_to_3_and_1(env, monkeypatch, error):
    @contextmanager
    def failing(settings):
        raise error
        yield

    monkeypatch.setattr(tcli, "session_factory", failing)
    result = invoke("build")
    assert result.exit_code == (3 if isinstance(error, WarehouseTransientError) else 1)
    assert env[1].calls == []


def test_usage_error_is_2(env):
    assert invoke("nope").exit_code == 2


def test_password_never_printed(env):
    for code in (0, 1, 2):
        env[1].code = code
        result = invoke("build")
        assert SENTINEL not in result.output
        assert SENTINEL not in (result.stderr_bytes or b"").decode()


# --- runner.open_session with a fake connection -------------------------------------------


class FakeConn:
    def __init__(self, lock_result):
        self.lock_result = lock_result
        self.statements = []
        self.closed = False

    def execute(self, query, params=None):
        self.statements.append(query)
        outer = self

        class Cursor:
            def fetchone(self):
                return (outer.lock_result,)

        return Cursor()

    def close(self):
        self.closed = True


def patch_connect(monkeypatch, conn):
    monkeypatch.setattr(rn, "check_environment", lambda: None)
    monkeypatch.setattr(rn, "connect", lambda *a, **k: conn)


def test_session_takes_and_releases_lock(monkeypatch):
    conn = FakeConn(True)
    patch_connect(monkeypatch, conn)
    with rn.open_session(object()):
        assert "pg_try_advisory_lock" in conn.statements[0]
    assert "pg_advisory_unlock" in conn.statements[-1] and conn.closed


def test_session_lock_busy_is_transient(monkeypatch):
    conn = FakeConn(False)
    patch_connect(monkeypatch, conn)
    with pytest.raises(WarehouseTransientError), rn.open_session(object()):
        pytest.fail("must not run dbt")
    assert conn.closed and not any("unlock" in s for s in conn.statements)


def test_session_preflight_transient_propagates(monkeypatch):
    monkeypatch.setattr(rn, "check_environment", lambda: None)

    def boom(*a, **k):
        raise WarehouseTransientError("connection refused")

    monkeypatch.setattr(rn, "connect", boom)
    with pytest.raises(WarehouseTransientError), rn.open_session(object()):
        pass


def test_default_project_dir_is_the_repo_transform_folder():
    path = rn.default_project_dir()
    assert isinstance(path, Path) and (path / "dbt_project.yml").is_file()


def test_child_env_injects_validated_host(env):
    environ, fake, _ = env
    environ["PITS_PG_HOST"] = "localhost"
    assert invoke("build").exit_code == 0
    assert fake.calls[0][1]["PITS_PG_HOST"] == "localhost"


def test_child_env_host_defaults_to_validated_loopback(env):
    assert invoke("build").exit_code == 0
    assert env[1].calls[0][1]["PITS_PG_HOST"] == "127.0.0.1"


def test_parse_child_env_has_no_host_override(env):
    env[0]["PITS_PG_HOST"] = "localhost"
    assert invoke("parse").exit_code == 0
    assert "PITS_PG_HOST" not in env[1].calls[0][1]


def test_lock_is_released_when_the_body_raises(monkeypatch):
    conn = FakeConn(True)
    patch_connect(monkeypatch, conn)
    with pytest.raises(RuntimeError), rn.open_session(object()):
        raise RuntimeError("body failed")
    assert "pg_advisory_unlock" in conn.statements[-1] and conn.closed


def test_runner_oserror_exits_1_and_releases_lock(env, monkeypatch):
    conn = FakeConn(True)
    patch_connect(monkeypatch, conn)
    monkeypatch.setattr(tcli, "session_factory", rn.open_session)

    def no_start(*a, **k):
        raise OSError("boom")

    monkeypatch.setattr(rn.subprocess, "run", no_start)
    monkeypatch.setattr(tcli, "dbt_runner", rn.subprocess_runner)
    result = invoke("build")
    assert result.exit_code == 1 and "could not start dbt (OSError)" in result.output
    assert "pg_advisory_unlock" in conn.statements[-1] and conn.closed


def test_dbt_executable_not_found_exits_1(env, monkeypatch, tmp_path):
    monkeypatch.setattr(rn.sys, "executable", str(tmp_path / "python"))
    monkeypatch.setattr(tcli, "executable_factory", rn.dbt_executable)
    for command in ("parse", "build"):
        result = invoke(command)
        assert result.exit_code == 1 and "dbt executable not found" in result.output
    assert env[1].calls == []


def test_dbt_executable_found_next_to_python(monkeypatch, tmp_path):
    (tmp_path / "dbt").write_text("")
    (tmp_path / "dbt.exe").write_text("")
    monkeypatch.setattr(rn.sys, "executable", str(tmp_path / "python"))
    assert Path(rn.dbt_executable()).parent == tmp_path


def test_subprocess_runner_maps_oserror(monkeypatch):
    def no_start(*a, **k):
        raise FileNotFoundError("x")

    monkeypatch.setattr(rn.subprocess, "run", no_start)
    with pytest.raises(rn.WarehouseConfigError, match="could not start dbt"):
        rn.subprocess_runner(["dbt"], {})

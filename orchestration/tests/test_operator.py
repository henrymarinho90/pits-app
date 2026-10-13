"""PitsCliOperator against a fake `pits` executable (a Python script), no real CLI involved."""

from __future__ import annotations

import json
import signal
import stat
import sys
import threading
import time
from pathlib import Path

import pytest
from airflow.sdk.exceptions import AirflowException, AirflowFailException

from pits_cli import operator as op_module
from pits_cli.operator import PARAM_ARGS, PitsCliOperator, build_env, extract_args, force_args

FAKE = f"""#!{sys.executable}
import json, os, signal, sys, time
from pathlib import Path

here = Path(__file__).parent
mode, *rest = sys.argv[1:]
if mode == "exit":
    print("fake stdout line")
    print("fake stderr line", file=sys.stderr)
    sys.exit(int(rest[0]))
if mode == "signal":
    os.kill(os.getpid(), signal.SIGKILL)
if mode == "dump":
    (here / "dump.json").write_text(json.dumps({{"env": dict(os.environ), "argv": sys.argv[1:]}}))
    sys.exit(0)
if mode in ("sleep", "sleep-ignore-term", "sleep-grandchild"):
    if mode == "sleep-grandchild":
        import subprocess
        grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        (here / "gpid.txt").write_text(str(grandchild.pid))
    if mode == "sleep-ignore-term":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    (here / "pid.txt").write_text(str(os.getpid()))
    print("ready", flush=True)
    time.sleep(60)
sys.exit(99)
"""


@pytest.fixture
def fake(tmp_path):
    path = tmp_path / "pits"
    path.write_text(FAKE)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def make(fake, command, **kwargs):
    kwargs.setdefault("env_allow", ["S3_*"])
    return PitsCliOperator(task_id="t", command=command, executable=str(fake), **kwargs)


def test_exit_zero_succeeds(fake):
    make(fake, ["exit", "0"]).execute({})


def test_exit_three_is_retryable(fake):
    with pytest.raises(AirflowException) as exc:
        make(fake, ["exit", "3"]).execute({})
    assert not isinstance(exc.value, AirflowFailException)
    assert "transient" in str(exc.value)


@pytest.mark.parametrize("code", [1, 2, 4, 137])
def test_other_exit_codes_fail_without_retry(fake, code):
    with pytest.raises(AirflowFailException):
        make(fake, ["exit", str(code)]).execute({})


def test_killed_by_signal_fails_without_retry(fake):
    with pytest.raises(AirflowFailException) as exc:
        make(fake, ["signal"]).execute({})
    assert "-9" in str(exc.value)


def test_missing_executable_fails_without_retry(tmp_path):
    operator = PitsCliOperator(
        task_id="t", command=["x"], env_allow=[], executable=str(tmp_path / "nope")
    )
    with pytest.raises(AirflowFailException):
        operator.execute({})


def test_child_output_reaches_the_task_log(fake, capsys):
    make(fake, ["exit", "0"]).execute({})  # the task logger writes to stdout (structlog)
    text = capsys.readouterr().out
    assert "fake stdout line" in text and "fake stderr line" in text


def test_env_allow_list_hides_airflow_and_foreign_secrets(fake, monkeypatch):
    monkeypatch.setenv("AIRFLOW__DATABASE__SQL_ALCHEMY_CONN_CMD", "x")
    monkeypatch.setenv("AIRFLOW__API_AUTH__JWT_SECRET", "jwt-secret")
    monkeypatch.setenv("AIRFLOW_METADB_PASSWORD", "metadb-secret")
    monkeypatch.setenv("PITS_PG_TRANSFORMER_PASSWORD", "transformer-secret")
    monkeypatch.setenv("PITS_PG_LOADER_PASSWORD", "loader-secret")
    monkeypatch.setenv("PITS_PG_HOST", "postgres")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "s3-secret")
    monkeypatch.setenv("SODA_APP_TOKEN", "soda-secret")
    monkeypatch.setenv("PGPASSWORD", "libpq-secret")
    monkeypatch.setenv("POSTGRES_PASSWORD", "admin-secret")
    make(fake, ["dump"], env_allow=["S3_*", "PITS_PG_HOST", "PITS_PG_LOADER_PASSWORD"]).execute({})
    seen = json.loads((fake.parent / "dump.json").read_text())["env"]
    assert seen["S3_SECRET_ACCESS_KEY"] == "s3-secret"
    assert seen["PITS_PG_LOADER_PASSWORD"] == "loader-secret"
    assert seen["PITS_PG_HOST"] == "postgres"
    assert "PATH" in seen
    forbidden = (
        "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN_CMD",
        "AIRFLOW__API_AUTH__JWT_SECRET",
        "AIRFLOW_METADB_PASSWORD",
        "PITS_PG_TRANSFORMER_PASSWORD",
        "SODA_APP_TOKEN",
        "PGPASSWORD",
        "POSTGRES_PASSWORD",
    )
    assert not [name for name in forbidden if name in seen]


def test_airflow_variables_never_pass_even_if_a_pattern_matches():
    source = {"AIRFLOW__CORE__FERNET_KEY": "k", "AIRFLOW_X": "1", "S3_A": "2"}
    assert build_env(source, ["*"]) == {"S3_A": "2"}


def test_secret_values_are_masked(fake, monkeypatch):
    masked = []
    monkeypatch.setattr(op_module, "mask_secret", masked.append)
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "s3-secret")
    monkeypatch.delenv("SODA_APP_TOKEN", raising=False)
    make(fake, ["exit", "0"], secret_env=["S3_SECRET_ACCESS_KEY", "SODA_APP_TOKEN"]).execute({})
    assert masked == ["s3-secret"]  # absent/empty secrets are skipped


def _start(operator):
    outcome = {}

    def run():
        try:
            operator.execute({})
        except BaseException as exc:  # noqa: BLE001 - the test inspects it
            outcome["error"] = exc

    thread = threading.Thread(target=run)
    thread.start()
    pid_file = Path(operator.executable).parent / "pid.txt"
    deadline = time.monotonic() + 10
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert pid_file.exists(), "fake child did not start"
    time.sleep(0.2)  # let the file be fully written
    return thread, outcome, int(pid_file.read_text())


def _is_dead(pid):
    """Gone, or a zombie waiting for its (non-reaping) parent: no longer running."""
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (FileNotFoundError, ProcessLookupError):
        # procfs returns ESRCH (ProcessLookupError) while the process is terminating.
        return True
    return state == "Z"


def _wait_for(path):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if path.exists() and path.read_text():
            return int(path.read_text())
        time.sleep(0.05)
    raise AssertionError(f"{path} was not written")


def _wait_dead(pid):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not _is_dead(pid):
        time.sleep(0.05)
    return _is_dead(pid)


def test_on_kill_terminates_the_child(fake):
    operator = make(fake, ["sleep"], kill_timeout=2)
    thread, outcome, pid = _start(operator)
    operator.on_kill()
    thread.join(10)
    assert not thread.is_alive()
    assert _is_dead(pid)
    assert isinstance(outcome["error"], AirflowFailException)
    assert "-15" in str(outcome["error"])  # SIGTERM


def test_on_kill_escalates_to_sigkill(fake):
    operator = make(fake, ["sleep-ignore-term"], kill_timeout=0.5)
    thread, outcome, pid = _start(operator)
    started = time.monotonic()
    operator.on_kill()
    thread.join(10)
    assert not thread.is_alive()
    assert time.monotonic() - started >= 0.5
    assert _is_dead(pid)
    assert "-9" in str(outcome["error"])


def test_task_timeout_kills_the_child(fake):
    """The task runner enforces execution_timeout with SIGALRM -> AirflowTaskTimeout raised inside
    execute (airflow.sdk.execution_time.timeout, 3.3.2). The child must not survive it."""
    from airflow.sdk.exceptions import AirflowTaskTimeout
    from airflow.sdk.execution_time.timeout import timeout

    operator = make(fake, ["sleep"])
    with pytest.raises(AirflowTaskTimeout), timeout(1):
        operator.execute({})
    assert _wait_dead(_wait_for(fake.parent / "pid.txt"))


def test_keyboard_interrupt_kills_the_child(fake):
    def interrupt(signum, frame):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGALRM, interrupt)
    signal.setitimer(signal.ITIMER_REAL, 1)
    try:
        with pytest.raises(KeyboardInterrupt):
            make(fake, ["sleep"]).execute({})
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    assert _wait_dead(_wait_for(fake.parent / "pid.txt"))


def test_timeout_escalates_to_sigkill_when_the_child_ignores_sigterm(fake):
    from airflow.sdk.exceptions import AirflowTaskTimeout
    from airflow.sdk.execution_time.timeout import timeout

    operator = make(fake, ["sleep-ignore-term"], kill_timeout=0.5)
    with pytest.raises(AirflowTaskTimeout), timeout(1):
        operator.execute({})
    assert _wait_dead(_wait_for(fake.parent / "pid.txt"))


def test_grandchild_in_the_same_group_dies_too(fake):
    """dbt is a child of pits: the group signal must reach it (timeout and on_kill paths)."""
    from airflow.sdk.exceptions import AirflowTaskTimeout
    from airflow.sdk.execution_time.timeout import timeout

    operator = make(fake, ["sleep-grandchild"])
    with pytest.raises(AirflowTaskTimeout), timeout(1):
        operator.execute({})
    assert _wait_dead(_wait_for(fake.parent / "pid.txt"))
    assert _wait_dead(_wait_for(fake.parent / "gpid.txt"))


def test_on_kill_kills_the_grandchild(fake):
    operator = make(fake, ["sleep-grandchild"])
    thread, _, pid = _start(operator)
    gpid = _wait_for(fake.parent / "gpid.txt")
    operator.on_kill()
    thread.join(10)
    assert _wait_dead(pid) and _wait_dead(gpid)


def test_child_gets_unbuffered_python(fake):
    make(fake, ["dump"]).execute({})
    assert json.loads((fake.parent / "dump.json").read_text())["env"]["PYTHONUNBUFFERED"] == "1"


def test_on_kill_without_child_is_a_noop(fake):
    make(fake, ["sleep"]).on_kill()


# --- params -> argv -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "since", "expected"),
    [
        ("incremental", None, []),
        ("incremental", "", []),
        ("full", None, ["--full"]),
        ("since", "2026-10-01", ["--since", "2026-10-01"]),
    ],
)
def test_extract_args_valid(mode, since, expected):
    assert extract_args(mode, since) == expected


@pytest.mark.parametrize(
    ("mode", "since"),
    [
        ("bogus", None),
        ("", None),
        ("since", None),
        ("since", ""),
        ("since", "2026-13-01"),
        ("since", "2026-1-1"),
        ("since", "20261001"),
        ("since", "--full"),
        ("since", "2026-10-01; rm -rf /"),
        ("incremental", "2026-10-01"),
        ("full", "2026-10-01"),
    ],
)
def test_extract_args_invalid(mode, since):
    with pytest.raises(ValueError):
        extract_args(mode, since)


def test_operator_builds_argv_from_params(fake):
    operator = make(fake, ["dump"], param_args="trm_extract")
    operator.execute({"params": {"extract_mode": "since", "since": "2026-10-01"}})
    argv = json.loads((fake.parent / "dump.json").read_text())["argv"]
    assert argv == ["dump", "--since", "2026-10-01"]


def test_operator_defaults_to_incremental_without_params(fake):
    make(fake, ["dump"], param_args="trm_extract").execute({})
    assert json.loads((fake.parent / "dump.json").read_text())["argv"] == ["dump"]


def test_operator_rejects_invalid_params_before_running(fake):
    operator = make(fake, ["dump"], param_args="trm_extract")
    with pytest.raises(AirflowFailException):
        operator.execute({"params": {"extract_mode": "since", "since": None}})
    assert not (fake.parent / "dump.json").exists()  # the child never started


@pytest.mark.parametrize(("value", "expected"), [(True, ["--force"]), (False, [])])
def test_force_args_valid(value, expected):
    assert force_args(value) == expected


@pytest.mark.parametrize("value", ["false", "true", "", 1, 0, None, [], {}])
def test_force_args_rejects_non_booleans(value):
    with pytest.raises(ValueError):
        force_args(value)


@pytest.mark.parametrize(
    ("params", "expected"),
    [({}, ["dump"]), ({"force": False}, ["dump"]), ({"force": True}, ["dump", "--force"])],
)
def test_operator_runt_param_args_builds_force(fake, params, expected):
    make(fake, ["dump"], param_args="runt_extract").execute({"params": params})
    assert json.loads((fake.parent / "dump.json").read_text())["argv"] == expected


def test_operator_runt_ignores_trm_params(fake):
    """Each translator reads only its own params: extract_mode means nothing for runt_extract."""
    make(fake, ["dump"], param_args="runt_extract").execute({"params": {"extract_mode": "full"}})
    assert json.loads((fake.parent / "dump.json").read_text())["argv"] == ["dump"]


@pytest.mark.parametrize("bad", ["yes", "false", 1, None])
def test_operator_rejects_non_boolean_force_before_running(fake, bad):
    operator = make(fake, ["dump"], param_args="runt_extract")
    with pytest.raises(AirflowFailException):
        operator.execute({"params": {"force": bad}})
    assert not (fake.parent / "dump.json").exists()


@pytest.mark.parametrize(
    ("params", "expected"),
    [({}, ["dump"]), ({"force": False}, ["dump"]), ({"force": True}, ["dump", "--force"])],
)
def test_operator_divipola_param_args_builds_force(fake, params, expected):
    make(fake, ["dump"], param_args="divipola_extract").execute({"params": params})
    assert json.loads((fake.parent / "dump.json").read_text())["argv"] == expected


@pytest.mark.parametrize("bad", ["yes", "false", 1, None])
def test_operator_divipola_rejects_non_boolean_force_before_running(fake, bad):
    operator = make(fake, ["dump"], param_args="divipola_extract")
    with pytest.raises(AirflowFailException):
        operator.execute({"params": {"force": bad}})
    assert not (fake.parent / "dump.json").exists()


def test_operator_without_param_args_ignores_params(fake):
    make(fake, ["dump"]).execute({"params": {"force": True, "extract_mode": "full"}})
    assert json.loads((fake.parent / "dump.json").read_text())["argv"] == ["dump"]


def test_unknown_param_args_name_is_rejected_at_definition():
    assert set(PARAM_ARGS) == {"trm_extract", "runt_extract", "divipola_extract"}
    with pytest.raises(ValueError, match="param_args"):
        PitsCliOperator(task_id="t", command=["x"], env_allow=[], param_args="bogus")


def test_kill_grace_is_below_the_supervisor_escalation_delay():
    """supervisor.py (3.3.2) escalates to SIGKILL on the task process after 5 s."""
    assert op_module.DEFAULT_KILL_TIMEOUT < 5

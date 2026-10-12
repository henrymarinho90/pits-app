"""Helpers for `-m airflow` (integration against the real core + orchestration stack).

Everything goes through `docker exec` on the scheduler (the Airflow CLI is the public surface):
no REST/JWT, no compose commands. `tests/orchestration_it` is on pytest's pythonpath, so the
test modules import this file directly (never from conftest).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEDULER = "pits-airflow-scheduler"
POSTGRES = "pits-postgres"
SEAWEEDFS = "pits-seaweedfs"
DAG_ID = "trm_daily"
LOGS = "/opt/airflow/logs"
ROOT = Path(__file__).resolve().parents[2]
RUN_SCRIPT = ROOT / "scripts" / "run_dag_and_wait.sh"
POLL_SECONDS = 5
LOCK_ACQUIRE_SECONDS = 30
# Absolute path: a bare "bash" can resolve to the WSL launcher in System32 on Windows.
BASH = shutil.which("bash") or "bash"
TERMINAL_STATES = {"success", "failed"}

# Every run id created by the tests; the session teardown reports the ones not finished.
CREATED_RUNS: list[str] = []


def run(cmd: list[str], *, timeout: float = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
    )


def docker_exec(
    *args: str, env: dict[str, str] | None = None, timeout: float = 120
) -> subprocess.CompletedProcess[str]:
    env_flags = [f for k, v in (env or {}).items() for f in ("-e", f"{k}={v}")]
    return run(["docker", "exec", *env_flags, SCHEDULER, *args], timeout=timeout)


def airflow_json(*args: str) -> list[dict]:
    """Run `airflow ... -o json`; the CLI prints graphviz warnings on stdout, so parse the line
    that starts with '['."""
    proc = docker_exec("airflow", *args, "-o", "json")
    assert proc.returncode == 0, f"airflow {' '.join(args[:2])} failed (exit {proc.returncode})"
    for line in proc.stdout.splitlines():
        if line.startswith("["):
            return json.loads(line)
    raise AssertionError(f"no JSON in the output of airflow {' '.join(args[:2])}")


def trigger(conf: dict | None = None, logical_date: datetime | None = None) -> str:
    """Trigger a manual run with a unique run_id; return it (does not wait)."""
    run_id = f"manual__it_{datetime.now(UTC):%Y%m%dT%H%M%S%f}"
    CREATED_RUNS.append(run_id)
    args = ["airflow", "dags", "trigger", "-o", "json", "-r", run_id]
    if conf is not None:
        args += ["-c", json.dumps(conf)]
    if logical_date is not None:
        args += ["-l", logical_date.isoformat()]
    proc = docker_exec(*args, DAG_ID)
    assert proc.returncode == 0, f"trigger failed (exit {proc.returncode})"
    return run_id


def runs() -> list[dict]:
    return airflow_json("dags", "list-runs", DAG_ID)


def run_state(run_id: str) -> str:
    return next((r["state"] for r in runs() if r["run_id"] == run_id), "unknown")


def task_states(run_id: str) -> dict[str, str]:
    rows = airflow_json("tasks", "states-for-dag-run", DAG_ID, run_id)
    return {r["task_id"]: r["state"] for r in rows}


def wait_until(predicate: Callable[[], bool], what: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while True:
        if predicate():
            return
        if time.monotonic() >= deadline:
            raise AssertionError(f"timeout after {timeout:.0f}s waiting for {what}")
        time.sleep(POLL_SECONDS)


def wait_task_state(run_id: str, task_id: str, state: str, timeout: float) -> None:
    wait_until(lambda: task_states(run_id).get(task_id) == state, f"{task_id} -> {state}", timeout)


def wait_run_state(run_id: str, state: str, timeout: float) -> None:
    wait_until(lambda: run_state(run_id) == state, f"run -> {state}", timeout)


def attempts(run_id: str, task_id: str) -> list[int]:
    folder = f"{LOGS}/dag_id={DAG_ID}/run_id={run_id}/task_id={task_id}"
    proc = docker_exec("bash", "-c", f"ls '{folder}' 2>/dev/null")
    return sorted(int(m.group(1)) for m in re.finditer(r"attempt=(\d+)\.log", proc.stdout))


def log_events(run_id: str, task_id: str, attempt: int) -> list[str]:
    """Messages (`event` and exception values) of a task attempt log (JSON lines)."""
    path = f"{LOGS}/dag_id={DAG_ID}/run_id={run_id}/task_id={task_id}/attempt={attempt}.log"
    proc = docker_exec("cat", path)
    assert proc.returncode == 0, f"cannot read the log of {task_id} attempt {attempt}"
    events = []
    for line in proc.stdout.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(str(record.get("event", "")))
        # The operator's verdict ("exited with code N ...") lives in the exception detail.
        events.extend(str(d.get("exc_value", "")) for d in record.get("error_detail") or [])
    return events


def load_outcome(run_id: str, attempt: int = 1) -> dict[str, str]:
    """Fields (key=value) of the `outcome=...` line of the load task."""
    for event in log_events(run_id, "load", attempt):
        if event.startswith("outcome="):
            return dict(pair.split("=", 1) for pair in event.split() if "=" in pair)
    raise AssertionError("no outcome= line in the load log")


def run_script(*, logical_date: str | None = None) -> tuple[int, str]:
    """scripts/run_dag_and_wait.sh trm_daily; returns (exit code, run_id)."""
    env = {**os.environ, "TIMEOUT_SECONDS": "600"}
    if logical_date:
        env["LOGICAL_DATE"] = logical_date
    proc = subprocess.run(
        [BASH, str(RUN_SCRIPT), DAG_ID],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=700,
    )
    match = re.search(r"run_id=(\S+)", proc.stdout)
    assert match, "the script did not print the run_id"
    CREATED_RUNS.append(match.group(1))
    return proc.returncode, match.group(1)


def health(container: str) -> str:
    return run(["docker", "inspect", "-f", "{{.State.Health.Status}}", container]).stdout.strip()


@contextmanager
def seaweedfs_stopped() -> Iterator[Callable[[], None]]:
    """`docker stop pits-seaweedfs`; yields `restore()` (idempotent). The finally always starts
    it again and waits for healthy, even if the stop itself failed halfway."""
    state = {"stopped": True}  # set before the stop: a half-done stop is still restored

    def restore() -> None:
        if not state["stopped"]:
            return
        proc = run(["docker", "start", SEAWEEDFS])
        assert proc.returncode == 0, "docker start pits-seaweedfs failed"
        state["stopped"] = False
        wait_until(lambda: health(SEAWEEDFS) == "healthy", "pits-seaweedfs healthy", 180)

    try:
        proc = run(["docker", "stop", SEAWEEDFS], timeout=90)
        assert proc.returncode == 0, "docker stop pits-seaweedfs failed (permission or daemon)"
        yield restore
    finally:
        restore()


class LockHolder:
    """Holds the D90 advisory lock on the real warehouse from a test session."""

    def __init__(self, conn, key: int) -> None:
        self._conn = conn
        self._key = key
        self.held = False

    def acquire(self) -> None:
        """pg_try_advisory_lock with a bounded retry: never blocks without limit."""
        deadline = time.monotonic() + LOCK_ACQUIRE_SECONDS
        while True:
            row = self._conn.execute("SELECT pg_try_advisory_lock(%s)", (self._key,)).fetchone()
            if row[0]:
                self.held = True
                return
            if time.monotonic() >= deadline:
                raise AssertionError(
                    f"could not take the warehouse lock in {LOCK_ACQUIRE_SECONDS}s"
                )
            time.sleep(1)

    def release(self) -> None:
        if self.held:
            self._conn.execute("SELECT pg_advisory_unlock(%s)", (self._key,))
            self.held = False

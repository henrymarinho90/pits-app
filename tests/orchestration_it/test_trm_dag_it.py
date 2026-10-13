"""trm_daily against the real stack (D92, D94): `-m airflow`, see conftest.py for how to run.

Order matters only for the last test (secrets scan runs after every run has written its logs).
The tests with `slow` in their name (3 and 4) wait for the DAG's real retry_delay (5 min, x2
backoff with jitter, D92; no per-run override exists: the only params are extract_mode and since).
There is no `slow` pytest marker; each of them takes about 10 minutes.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest
from airflow_support import (
    DAG_ID,
    attempts,
    docker_exec,
    load_outcome,
    log_events,
    run_script,
    run_state,
    seaweedfs_stopped,
    task_states,
    trigger,
    wait_run_state,
    wait_task_state,
    wait_until,
)

TASKS = {"extract", "normalize", "load", "build", "freshness"}
FX_COLUMNS = "rate_date, currency_from, currency_to, rate, source_system, source_reference, load_id"
# retry_delay 5 min, exponential x2 with jitter (D92): the first retry lands 300-599 s after the
# failure; margin for the task itself.
RETRY_WAIT_SECONDS = 900


@pytest.fixture(scope="module")
def first_run() -> str:
    code, run_id = run_script()
    assert code == 0, f"run_dag_and_wait.sh exit {code}"
    return run_id


@pytest.fixture(scope="module")
def second_run(first_run) -> str:
    code, run_id = run_script()
    assert code == 0, f"run_dag_and_wait.sh exit {code}"
    assert run_id != first_run
    return run_id


def test_1_triggered_run_all_tasks_success(first_run):
    assert run_state(first_run) == "success"
    assert task_states(first_run) == dict.fromkeys(TASKS, "success")


def test_2_second_run_is_idempotent_and_mart_matches_landing(second_run, warehouse_admin):
    outcome = load_outcome(second_run)
    assert outcome["outcome"] in {"loaded", "already_loaded"}
    assert (outcome["inserted"], outcome["updated"], outcome["deleted"]) == ("0", "0", "0")

    # pits_reader cannot read landing, so the comparison runs as admin (read-only session).
    mart = f"SELECT {FX_COLUMNS} FROM marts.fct_fx_rate_daily"
    landing = f"SELECT {FX_COLUMNS} FROM landing.fx_rate"
    assert warehouse_admin.execute(f"SELECT count(*) FROM ({mart}) m").fetchone()[0] > 0
    for left, right in ((mart, landing), (landing, mart)):
        diff = warehouse_admin.execute(
            f"SELECT count(*) FROM (({left}) EXCEPT ALL ({right})) d"
        ).fetchone()[0]
        assert diff == 0


def test_3_slow_warehouse_lock_held_load_retries_then_succeeds(lock_holder):
    lock_holder.acquire()
    try:
        run_id = trigger()
        wait_task_state(run_id, "load", "up_for_retry", timeout=300)
        assert attempts(run_id, "load") == [1]
        assert any("exited with code 3" in e for e in log_events(run_id, "load", 1))
        assert task_states(run_id)["build"] != "success"
    finally:
        lock_holder.release()
    wait_run_state(run_id, "success", timeout=RETRY_WAIT_SECONDS)
    assert attempts(run_id, "load") == [1, 2]
    assert task_states(run_id) == dict.fromkeys(TASKS, "success")


def test_4_slow_seaweedfs_down_extract_retries_then_succeeds():
    with seaweedfs_stopped() as restore:
        run_id = trigger()
        wait_task_state(run_id, "extract", "up_for_retry", timeout=420)
        assert attempts(run_id, "extract") == [1]
        assert any("exited with code 3" in e for e in log_events(run_id, "extract", 1))
        restore()
        wait_run_state(run_id, "success", timeout=RETRY_WAIT_SECONDS)
    assert attempts(run_id, "extract") == [1, 2]


def test_5_wrong_transformer_password_is_permanent_failure():
    """`airflow tasks test` runs the real operator in-process with an env override that lives
    only in this `docker exec`: .env and the containers are untouched and no DagRun is stored.
    It exits 0 even when the task fails, so the verdict is read from the output: the exit code 1
    of pits (auth rejected after the handshake) must raise AirflowFailException, which Airflow
    never retries (try_number 1 -> failed). A retry would need the transient exit 3."""
    bad = "wrong-password-for-it-test"
    logical = datetime.now(UTC).replace(microsecond=0).isoformat()
    proc = docker_exec(
        "airflow",
        "tasks",
        "test",
        DAG_ID,
        "build",
        logical,
        env={"PITS_PG_TRANSFORMER_PASSWORD": bad},
        timeout=300,
    )
    out = proc.stdout + proc.stderr
    assert (
        "pits transform build --select tag:fx_rate exited with code 1 (permanent, no retry)" in out
    )
    assert "AirflowFailException" in out
    assert "will retry" not in out
    assert "new_state=failed" in out
    assert bad not in out


def test_6_clear_load_reruns_idempotently():
    logical = datetime.now(UTC).replace(microsecond=0)
    run_id = trigger(logical_date=logical)
    wait_run_state(run_id, "success", timeout=300)
    assert attempts(run_id, "load") == [1]

    window = (
        "-s",
        (logical - timedelta(minutes=1)).isoformat(),
        "-e",
        (logical + timedelta(minutes=1)).isoformat(),
    )
    proc = docker_exec("airflow", "tasks", "clear", "-t", "load", "-y", *window, DAG_ID)
    assert proc.returncode == 0, f"airflow tasks clear exit {proc.returncode}"

    wait_until(lambda: attempts(run_id, "load") == [1, 2], "load attempt 2", 120)
    wait_run_state(run_id, "success", timeout=300)
    assert task_states(run_id)["load"] == "success"
    outcome = load_outcome(run_id, attempt=2)
    assert outcome["outcome"] in {"loaded", "already_loaded"}
    assert (outcome["inserted"], outcome["updated"], outcome["deleted"]) == ("0", "0", "0")


SCAN_VARS = (
    "PITS_PG_LOADER_PASSWORD",
    "PITS_PG_TRANSFORMER_PASSWORD",
    "S3_SECRET_ACCESS_KEY",
    "S3_ACCESS_KEY_ID",
    "SODA_APP_TOKEN",
    "AIRFLOW_METADB_PASSWORD",
    "AIRFLOW__API_AUTH__JWT_SECRET",
    "AIRFLOW__API__SECRET_KEY",
    "AIRFLOW__CORE__FERNET_KEY",
)
REQUIRED_SCAN_VARS = SCAN_VARS[:3]
SCAN = (
    f"for v in {' '.join(SCAN_VARS)}; do "
    'if [ -z "${!v+x}" ]; then echo "$v unset"; '
    'elif [ -z "${!v}" ]; then echo "$v empty"; '
    'else val="${!v}"; echo "$v $(grep -rlF -- "$val" /opt/airflow/logs | wc -l)"; fi; done'
)


def test_7_no_secret_in_logs():
    """Prints only counts per variable name, never values. `unset`/`empty` mean nothing to scan."""
    proc = docker_exec("bash", "-c", SCAN, timeout=300)
    assert proc.returncode == 0
    rows = dict(line.split() for line in proc.stdout.splitlines() if re.fullmatch(r"\w+ \w+", line))
    print("secret scan (files containing the value):", rows)
    assert set(rows) == set(SCAN_VARS)
    for name in REQUIRED_SCAN_VARS:
        assert rows[name] == "0", f"{name}: {rows[name]}"
    for name, result in rows.items():
        assert result in {"0", "unset", "empty"}, f"{name}: {result}"

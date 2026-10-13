"""Fixtures for `-m airflow` (integration against the real core + orchestration stack).

Helpers live in airflow_support.py. The warehouse is only touched read-only (or to hold the D90
lock) as admin from the host (loopback), exactly like the pg tests; no database or role is created.
Run: `uv run --env-file ../pits-app/.env pytest -m airflow -q` (needs bash and docker on PATH).
Runs must be sequential: the DAG has max_active_runs=1.
"""

from __future__ import annotations

import warnings
from datetime import UTC, datetime, timedelta

import pytest
from airflow_support import (
    CREATED_RUNS,
    DAG_IDS,
    POSTGRES,
    SCHEDULER,
    SEAWEEDFS,
    TERMINAL_STATES,
    LockHolder,
    airflow_json,
    run,
    runs,
)

SCHEDULE_GUARD = timedelta(minutes=15)  # around each scheduled run
SCHEDULE_HOURS_UTC = (15, 16)  # trm_daily 10:00 and runt_fleet_snapshot 11:00 America/Bogota


def pytest_collection_modifyitems(items):
    for item in items:
        if "tests/orchestration_it/" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.airflow)


def _near_schedule(now: datetime) -> bool:
    base = now.replace(minute=0, second=0, microsecond=0)
    return any(
        abs(now - (base.replace(hour=hour) + timedelta(days=offset))) < SCHEDULE_GUARD
        for hour in SCHEDULE_HOURS_UTC
        for offset in (-1, 0, 1)
    )


@pytest.fixture(scope="session", autouse=True)
def _stack_up():
    """Fail fast if the stack is not ready for sequential runs; report unfinished runs at end."""
    proc = run(["docker", "ps", "--format", "{{.Names}}"])
    missing = {SCHEDULER, POSTGRES, SEAWEEDFS} - set(proc.stdout.split())
    if proc.returncode != 0 or missing:
        pytest.fail(f"stack not up (core + orchestration profiles); missing: {sorted(missing)}")
    listed = {d["dag_id"]: d for d in airflow_json("dags", "list")}
    for dag_id in DAG_IDS:
        if dag_id not in listed:
            pytest.fail(f"DAG {dag_id} not found (is the image rebuilt and the stack recreated?)")
        if str(listed[dag_id]["is_paused"]).lower() == "true":
            pytest.fail(f"DAG {dag_id} is paused: unpause it first")
        active = [r["run_id"] for r in runs(dag_id) if r["state"] in {"running", "queued"}]
        if active:
            pytest.fail(f"{len(active)} run(s) of {dag_id} running or queued (max_active_runs=1)")
    if _near_schedule(datetime.now(UTC)):
        pytest.fail(
            "within 15 min of a scheduled run (15:00 UTC trm_daily, 16:00 UTC "
            "runt_fleet_snapshot): "
            "run these tests later"
        )
    yield
    states = {r["run_id"]: r["state"] for dag_id in DAG_IDS for r in runs(dag_id)}
    unfinished = {
        i: states.get(i, "unknown") for i in CREATED_RUNS if states.get(i) not in TERMINAL_STATES
    }
    if unfinished:
        warnings.warn(f"runs created by the tests not finished: {unfinished}", stacklevel=1)


@pytest.fixture(scope="session")
def warehouse_admin():
    """Read-only admin connection to the REAL pits_warehouse (loopback, like the pg tests)."""
    from pg_support import _admin_base

    from pits.warehouse.connection import connect
    from pits.warehouse.settings import Profile

    conn = connect(_admin_base(), Profile.ADMIN, autocommit=True)
    conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    yield conn
    conn.close()


@pytest.fixture
def lock_holder():
    from pg_support import _admin_base

    from pits.warehouse.connection import connect
    from pits.warehouse.locks import WAREHOUSE_LOCK_KEY
    from pits.warehouse.settings import Profile

    conn = connect(_admin_base(), Profile.ADMIN, autocommit=True)
    try:
        yield LockHolder(conn, WAREHOUSE_LOCK_KEY)
    finally:
        conn.close()  # a session lock dies with its connection

"""runt_fleet_snapshot (D102) and trm_daily against the real stack: `-m airflow`.

See conftest.py for how to run. Test names carry `runt` so that `-k test_3` selects only the TRM
test of test_trm_dag_it.py. The forced run (test_runt_2) creates a raw batch of about 50 MB in
pits-raw that is never deleted (D74/D67), so it only runs with PITS_IT_FORCE=1 and the suite must
never contain a second force. Test 1 runs against the current state of the source: while the
publication has not changed, extract ends `unchanged`, normalize `already_present` and load
`already_loaded`.
"""

from __future__ import annotations

import os

import pytest
from airflow_support import (
    DAG_ID,
    RUNT_DAG_ID,
    run_script,
    run_state,
    task_outcomes,
    task_states,
)

TASKS = {"extract", "normalize", "load", "build", "freshness"}
TIMEOUT = 1500  # the forced run downloads and re-normalizes the whole snapshot

# Per publication (coverage_from = first day of the month), like
# transform/tests/assert_vehicle_fleet_rows_match_load_run.sql: a new month must not break these.
LATEST_RUN = (
    "SELECT DISTINCT ON (coverage_from) coverage_from, row_count, load_id FROM ops.load_run "
    "WHERE dataset = 'vehicle_fleet_snapshot' ORDER BY coverage_from, load_id DESC"
)
ROWS_BY_PUBLICATION = (
    "SELECT make_date(publication_year::int, publication_month::int, 1), count(*), "
    "min(load_id), max(load_id) FROM {table} GROUP BY 1"
)
TABLES = {"landing": "landing.vehicle_fleet_snapshot", "mart": "marts.fct_vehicle_fleet_snapshot"}


def _fleet_state(warehouse_admin) -> dict:
    """Per publication: the latest load_run (rows, load_id) and what landing and the mart hold."""
    latest = {d: (rows, load_id) for d, rows, load_id in warehouse_admin.execute(LATEST_RUN)}
    state = {
        "load_runs": warehouse_admin.execute(
            "SELECT count(*) FROM ops.load_run WHERE dataset = 'vehicle_fleet_snapshot'"
        ).fetchone()[0],
        "latest": latest,
    }
    for name, table in TABLES.items():
        found = warehouse_admin.execute(ROWS_BY_PUBLICATION.format(table=table))
        state[name] = {d: (n, low, high) for d, n, low, high in found}
    return state


def _assert_warehouse_consistent(state: dict) -> None:
    assert state["latest"], "no vehicle_fleet_snapshot load_run in the warehouse"
    expected = {d: (rows, load_id, load_id) for d, (rows, load_id) in state["latest"].items()}
    assert state["landing"] == expected  # every row of a publication carries its latest load_id
    assert state["mart"] == expected  # and the mart is a copy of it


@pytest.fixture(scope="module")
def first_run() -> str:
    code, run_id = run_script(dag_id=RUNT_DAG_ID, timeout_seconds=TIMEOUT)
    assert code == 0, f"run_dag_and_wait.sh exit {code}"
    return run_id


def test_runt_1_full_run_succeeds_and_is_idempotent(first_run, warehouse_admin):
    assert run_state(first_run, RUNT_DAG_ID) == "success"
    assert task_states(first_run, RUNT_DAG_ID) == dict.fromkeys(TASKS, "success")

    (extract,) = task_outcomes(first_run, "extract", dag_id=RUNT_DAG_ID)
    normalize = task_outcomes(first_run, "normalize", dag_id=RUNT_DAG_ID)
    load = task_outcomes(first_run, "load", dag_id=RUNT_DAG_ID)
    assert extract["outcome"] in {"unchanged", "committed"}
    assert normalize and load
    if extract["outcome"] == "unchanged":
        assert {o["outcome"] for o in normalize} == {"already_present"}
        assert {o["outcome"] for o in load} == {"already_loaded"}
        assert {(o["inserted"], o["updated"], o["deleted"]) for o in load} == {("0", "0", "0")}
    _assert_warehouse_consistent(_fleet_state(warehouse_admin))


@pytest.mark.skipif(
    os.environ.get("PITS_IT_FORCE") != "1",
    reason="force=true stores a ~50 MB raw batch (never deleted): set PITS_IT_FORCE=1 to run it",
)
def test_runt_2_force_creates_a_new_raw_batch_and_the_chain_still_succeeds(
    first_run, warehouse_admin, capsys
):
    """What really happens with force=true is printed (and recorded in docs/06_status.md): the
    assertions only pin what must hold either way."""
    (before,) = task_outcomes(first_run, "extract", dag_id=RUNT_DAG_ID)
    state_before = _fleet_state(warehouse_admin)

    code, run_id = run_script(dag_id=RUNT_DAG_ID, conf={"force": True}, timeout_seconds=TIMEOUT)
    assert code == 0, f"run_dag_and_wait.sh exit {code}"
    assert task_states(run_id, RUNT_DAG_ID) == dict.fromkeys(TASKS, "success")

    (extract,) = task_outcomes(run_id, "extract", dag_id=RUNT_DAG_ID)
    assert extract["outcome"] == "committed"  # a new batch even though the source did not change
    assert extract["batch_id"] != before["batch_id"]
    assert extract["rows"] == before["rows"]

    normalize = task_outcomes(run_id, "normalize", dag_id=RUNT_DAG_ID)
    load = task_outcomes(run_id, "load", dag_id=RUNT_DAG_ID)
    assert {o["outcome"] for o in normalize} <= {"created", "already_present"}
    assert {o["outcome"] for o in load} <= {"loaded", "already_loaded"}
    state_after = _fleet_state(warehouse_admin)
    _assert_warehouse_consistent(state_after)
    rows = {d: r for d, (r, _) in state_after["latest"].items()}
    assert rows == {d: r for d, (r, _) in state_before["latest"].items()}  # same content

    with capsys.disabled():
        print("force=true extract:", extract)
        print("force=true normalize:", normalize)
        print("force=true load:", load)
        print("warehouse before:", state_before)
        print("warehouse after:", state_after)


def test_runt_3_trm_daily_still_succeeds():
    """The D101 selectors in build/freshness must not break the TRM pipeline."""
    code, run_id = run_script(dag_id=DAG_ID)
    assert code == 0, f"run_dag_and_wait.sh exit {code}"
    assert task_states(run_id, DAG_ID) == dict.fromkeys(TASKS, "success")

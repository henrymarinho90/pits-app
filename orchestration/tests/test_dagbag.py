"""Static checks of the DAG definitions (no scheduler, no database)."""

from __future__ import annotations

import re
from datetime import timedelta
from importlib.metadata import version
from pathlib import Path

import pytest
from airflow.dag_processing.dagbag import DagBag
from airflow.sdk.exceptions import ParamValidationError

ROOT = Path(__file__).resolve().parents[2]
DAGS = ROOT / "orchestration" / "dags"
CHAIN = ["extract", "normalize", "load", "build", "freshness"]


@pytest.fixture(scope="module")
def dagbag():
    return DagBag(dag_folder=str(DAGS))


@pytest.fixture(scope="module")
def dag(dagbag):
    return dagbag.dags["trm_daily"]


def test_no_import_errors(dagbag):
    assert dagbag.import_errors == {}
    assert sorted(dagbag.dags) == ["runt_fleet_snapshot", "trm_daily"]


def test_linear_chain_of_five_tasks(dag):
    assert sorted(dag.task_ids) == sorted(CHAIN)
    for index, task_id in enumerate(CHAIN):
        task = dag.get_task(task_id)
        expected_up = {CHAIN[index - 1]} if index else set()
        expected_down = {CHAIN[index + 1]} if index < len(CHAIN) - 1 else set()
        assert task.upstream_task_ids == expected_up
        assert task.downstream_task_ids == expected_down


def test_dag_level_settings(dag):
    assert dag.catchup is False
    assert dag.max_active_runs == 1
    assert dag.dagrun_timeout == timedelta(minutes=90)
    assert str(dag.timezone) == "America/Bogota"
    assert dag.start_date is not None and dag.start_date.tzinfo is not None
    assert dag.start_date.year == 2026


def test_schedule_is_10_00_bogota(dag):
    timetable = dag.timetable
    assert type(timetable).__name__ == "CronTriggerTimetable"
    assert "0 10 * * *" in repr(timetable)
    assert "America/Bogota" in repr(timetable)


def test_params_defaults(dag):
    assert dag.params.dump() == {"extract_mode": "incremental", "since": None}


@pytest.mark.parametrize(
    ("key", "value"),
    [("extract_mode", "bogus"), ("since", "10/01/2026"), ("since", 20261001)],
)
def test_params_schema_rejects_bad_values(dag, key, value):
    with pytest.raises(ParamValidationError):
        dag.params.get_param(key).resolve(value)


@pytest.mark.parametrize(
    ("key", "value"),
    [("extract_mode", "full"), ("extract_mode", "since"), ("since", "2026-10-01"), ("since", None)],
)
def test_params_schema_accepts_good_values(dag, key, value):
    assert dag.params.get_param(key).resolve(value) == value


@pytest.mark.parametrize("task_id", CHAIN)
def test_retries_and_backoff(dag, task_id):
    task = dag.get_task(task_id)
    assert task.retries == 3
    assert task.retry_delay == timedelta(minutes=5)
    assert task.retry_exponential_backoff == 2.0
    assert task.max_retry_delay == timedelta(minutes=30)


@pytest.mark.parametrize(
    ("task_id", "minutes"),
    [("extract", 15), ("normalize", 10), ("load", 10), ("build", 20), ("freshness", 5)],
)
def test_execution_timeouts(dag, task_id, minutes):
    assert dag.get_task(task_id).execution_timeout == timedelta(minutes=minutes)


@pytest.mark.parametrize(
    ("task_id", "pool"),
    [
        ("extract", "default_pool"),
        ("normalize", "default_pool"),
        ("load", "pits_warehouse"),
        ("build", "pits_warehouse"),
        ("freshness", "pits_warehouse"),
    ],
)
def test_pools(dag, task_id, pool):
    task = dag.get_task(task_id)
    assert task.pool == pool
    assert task.pool_slots == 1


def test_env_allow_lists_match_d92(dag):
    allow = {t: set(dag.get_task(t).env_allow) for t in CHAIN}
    warehouse = {"PITS_PG_HOST", "POSTGRES_HOST_PORT", "PITS_WAREHOUSE_DB"}
    assert allow["extract"] == {"S3_*", "SODA_*"}
    assert allow["normalize"] == {"S3_*"}
    assert allow["load"] == {"S3_*", "PITS_PG_LOADER_PASSWORD"} | warehouse
    assert allow["build"] == {"PITS_PG_TRANSFORMER_PASSWORD"} | warehouse
    assert allow["freshness"] == allow["build"]
    for task_id in CHAIN:
        assert not any(p.upper().startswith("AIRFLOW") for p in allow[task_id])


def test_commands(dag):
    commands = {t: dag.get_task(t).command for t in CHAIN}
    assert commands == {
        "extract": ["extract", "trm"],
        "normalize": ["normalize", "trm"],
        "load": ["load", "fx-rate"],
        # D101: without the selector, freshness would also evaluate the fleet source.
        "build": ["transform", "build", "--select", "tag:fx_rate"],
        "freshness": ["transform", "freshness", "--select", "tag:fx_rate"],
    }
    assert dag.get_task("extract").param_args == "trm_extract"
    assert all(dag.get_task(t).param_args is None for t in CHAIN[1:])
    assert all(dag.get_task(t).executable == "/opt/pits/.venv/bin/pits" for t in CHAIN)


# --- runt_fleet_snapshot (D102) ---------------------------------------------------------------


@pytest.fixture(scope="module")
def runt(dagbag):
    return dagbag.dags["runt_fleet_snapshot"]


def test_runt_linear_chain_of_five_tasks(runt):
    assert sorted(runt.task_ids) == sorted(CHAIN)
    for index, task_id in enumerate(CHAIN):
        task = runt.get_task(task_id)
        assert task.upstream_task_ids == ({CHAIN[index - 1]} if index else set())
        last = index == len(CHAIN) - 1
        assert task.downstream_task_ids == (set() if last else {CHAIN[index + 1]})


def test_runt_dag_level_settings(runt):
    assert runt.catchup is False
    assert runt.max_active_runs == 1
    assert runt.dagrun_timeout == timedelta(minutes=120)
    assert str(runt.timezone) == "America/Bogota"
    assert runt.start_date is not None and runt.start_date.tzinfo is not None


def test_runt_schedule_is_11_00_bogota(runt):
    timetable = runt.timetable
    assert type(timetable).__name__ == "CronTriggerTimetable"
    assert "0 11 * * *" in repr(timetable)
    assert "America/Bogota" in repr(timetable)


def test_runt_params_force_is_a_boolean_defaulting_to_false(runt):
    assert runt.params.dump() == {"force": False}
    param = runt.params.get_param("force")
    assert param.resolve(True) is True
    for bad in ("yes", "false", 1, None):
        with pytest.raises(ParamValidationError):
            param.resolve(bad)


@pytest.mark.parametrize("task_id", CHAIN)
def test_runt_retries_and_backoff_follow_d92(runt, task_id):
    task = runt.get_task(task_id)
    assert task.retries == 3
    assert task.retry_delay == timedelta(minutes=5)
    assert task.retry_exponential_backoff == 2.0
    assert task.max_retry_delay == timedelta(minutes=30)


@pytest.mark.parametrize(
    ("task_id", "minutes"),
    [("extract", 30), ("normalize", 15), ("load", 15), ("build", 20), ("freshness", 5)],
)
def test_runt_execution_timeouts(runt, task_id, minutes):
    assert runt.get_task(task_id).execution_timeout == timedelta(minutes=minutes)


@pytest.mark.parametrize(
    ("task_id", "pool"),
    [
        ("extract", "default_pool"),
        ("normalize", "default_pool"),
        ("load", "pits_warehouse"),
        ("build", "pits_warehouse"),
        ("freshness", "pits_warehouse"),
    ],
)
def test_runt_pools(runt, task_id, pool):
    task = runt.get_task(task_id)
    assert task.pool == pool
    assert task.pool_slots == 1


def test_runt_env_allow_lists(runt):
    allow = {t: set(runt.get_task(t).env_allow) for t in CHAIN}
    warehouse = {"PITS_PG_HOST", "POSTGRES_HOST_PORT", "PITS_WAREHOUSE_DB"}
    assert allow["extract"] == {"S3_*", "SODA_*"}
    assert allow["normalize"] == {"S3_*"}
    assert allow["load"] == {"S3_*", "PITS_PG_LOADER_PASSWORD"} | warehouse
    assert allow["build"] == {"PITS_PG_TRANSFORMER_PASSWORD"} | warehouse
    assert allow["freshness"] == allow["build"]
    for task_id in CHAIN:
        assert not any(p.upper().startswith("AIRFLOW") for p in allow[task_id])


def test_runt_commands_and_param_args(runt):
    commands = {t: runt.get_task(t).command for t in CHAIN}
    assert commands == {
        "extract": ["extract", "runt"],
        "normalize": ["normalize", "runt"],
        "load": ["load", "vehicle-fleet"],
        "build": ["transform", "build", "--select", "tag:vehicle_fleet"],
        "freshness": ["transform", "freshness", "--select", "tag:vehicle_fleet"],
    }
    assert runt.get_task("extract").param_args == "runt_extract"
    assert all(runt.get_task(t).param_args is None for t in CHAIN[1:])
    assert all(runt.get_task(t).executable == "/opt/pits/.venv/bin/pits" for t in CHAIN)


def test_runt_force_param_becomes_the_force_flag(runt, tmp_path):
    """The DAG param reaches argv through the real extract task (fake executable, no CLI)."""
    import json
    import stat
    import sys

    fake = tmp_path / "pits"
    argv_file = tmp_path / "argv.json"
    fake.write_text(
        f"""#!{sys.executable}
import json, sys
open({str(argv_file)!r}, "w").write(json.dumps(sys.argv[1:]))
"""
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    task = runt.get_task("extract")
    original = task.executable
    task.executable = str(fake)
    try:
        cases = [({"force": True}, ["extract", "runt", "--force"]), ({}, ["extract", "runt"])]
        for params, expected in cases:
            task.execute({"params": params})
            assert json.loads(argv_file.read_text()) == expected
    finally:
        task.executable = original


def test_airflow_version_matches_dockerfile_and_pin():
    """Drift guard: the image base, the locked test environment and the pin must agree."""
    dockerfile = (ROOT / "docker" / "airflow" / "Dockerfile").read_text()
    match = re.search(r"^FROM apache/airflow:slim-(\d+\.\d+\.\d+)-python", dockerfile, re.M)
    assert match, "FROM apache/airflow:slim-<version>-python... not found in the Dockerfile"
    assert version("apache-airflow") == match.group(1) == "3.3.2"
    pyproject = (ROOT / "orchestration" / "pyproject.toml").read_text()
    assert f'"apache-airflow=={match.group(1)}"' in pyproject

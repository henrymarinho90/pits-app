"""runt_fleet_snapshot (D102): RUNT fleet extract -> normalize -> load -> dbt build -> freshness.

Same shape as trm_daily (D92): a linear chain, every step idempotent, the warehouse steps
serialized through the pool `pits_warehouse` (1 slot; the D90 advisory lock stays the safety net).
The source publishes a monthly snapshot, so most daily runs end `unchanged` (extract),
`already_present` (normalize) and `already_loaded` (load): a cheap check, not a reload.
build and freshness are limited to `tag:vehicle_fleet` (D101) so this DAG never touches fx_rate.
`force` (default False) makes extract store a NEW raw batch (about 50 MB) even if the source did
not change: a manual recovery tool, never part of the schedule.
"""

from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.sdk import DAG, CronTriggerTimetable, Param

from pits_cli.operator import PitsCliOperator

DAG_ID = "runt_fleet_snapshot"
TIMEZONE = "America/Bogota"  # UTC-5 all year (no DST): 11:00 local == 16:00 UTC
SCHEDULE_CRON = "0 11 * * *"
POOL = "pits_warehouse"
SELECT = ["--select", "tag:vehicle_fleet"]

S3_ENV = ["S3_*"]
SODA_ENV = ["SODA_*"]
WAREHOUSE_ENV = ["PITS_PG_HOST", "POSTGRES_HOST_PORT", "PITS_WAREHOUSE_DB"]
S3_SECRETS = ["S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"]
SODA_SECRETS = ["SODA_APP_TOKEN"]

default_args = {
    "owner": "data-platform",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": 2.0,
    "max_retry_delay": timedelta(minutes=30),
}

with DAG(
    dag_id=DAG_ID,
    description="Daily RUNT fleet pipeline: raw -> normalized -> landing -> dbt (D102)",
    schedule=CronTriggerTimetable(SCHEDULE_CRON, timezone=TIMEZONE),
    start_date=pendulum.datetime(2026, 10, 1, tz=TIMEZONE),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=120),
    default_args=default_args,
    params={
        "force": Param(
            False,
            type="boolean",
            description="Store a new raw batch even if the source did not change (about 50 MB).",
        ),
    },
    tags=["runt", "pits"],
) as dag:
    extract = PitsCliOperator(
        task_id="extract",
        command=["extract", "runt"],
        env_allow=[*S3_ENV, *SODA_ENV],
        secret_env=[*S3_SECRETS, *SODA_SECRETS],
        param_args="runt_extract",
        execution_timeout=timedelta(minutes=30),
    )
    normalize = PitsCliOperator(
        task_id="normalize",
        command=["normalize", "runt"],
        env_allow=S3_ENV,
        secret_env=S3_SECRETS,
        execution_timeout=timedelta(minutes=15),
    )
    load = PitsCliOperator(
        task_id="load",
        command=["load", "vehicle-fleet"],
        env_allow=[*S3_ENV, *WAREHOUSE_ENV, "PITS_PG_LOADER_PASSWORD"],
        secret_env=[*S3_SECRETS, "PITS_PG_LOADER_PASSWORD"],
        pool=POOL,
        execution_timeout=timedelta(minutes=15),
    )
    build = PitsCliOperator(
        task_id="build",
        command=["transform", "build", *SELECT],
        env_allow=[*WAREHOUSE_ENV, "PITS_PG_TRANSFORMER_PASSWORD"],
        secret_env=["PITS_PG_TRANSFORMER_PASSWORD"],
        pool=POOL,
        execution_timeout=timedelta(minutes=20),
    )
    # dbt exits 0 on WARN (35 days) and 1 on ERROR (65 days) -> pits exit 1 -> the run fails.
    freshness = PitsCliOperator(
        task_id="freshness",
        command=["transform", "freshness", *SELECT],
        env_allow=[*WAREHOUSE_ENV, "PITS_PG_TRANSFORMER_PASSWORD"],
        secret_env=["PITS_PG_TRANSFORMER_PASSWORD"],
        pool=POOL,
        execution_timeout=timedelta(minutes=5),
    )

    extract >> normalize >> load >> build >> freshness

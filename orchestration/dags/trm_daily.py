"""trm_daily (D92): TRM extract -> normalize -> load -> dbt build -> source freshness.

Linear chain; every step is idempotent and the load/transform steps serialize through the
pool `pits_warehouse` (1 slot). The pool does NOT replace the advisory lock of D90: it only
avoids queued tasks colliding; the lock remains the safety net (a busy lock exits 3 -> retry).
build and freshness are limited to `tag:fx_rate` (D101): without the selector, freshness would
also evaluate the vehicle fleet source, which this DAG does not refresh.
`logical_date` is not passed to the CLI: the extract is incremental from its own watermark.
"""

from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.sdk import DAG, CronTriggerTimetable, Param

from pits_cli.operator import PitsCliOperator

DAG_ID = "trm_daily"
TIMEZONE = "America/Bogota"  # UTC-5 all year (no DST): 10:00 local == 15:00 UTC
SCHEDULE_CRON = "0 10 * * *"
POOL = "pits_warehouse"

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
    description="Daily TRM pipeline: raw -> normalized -> landing -> dbt (D92)",
    schedule=CronTriggerTimetable(SCHEDULE_CRON, timezone=TIMEZONE),
    start_date=pendulum.datetime(2026, 10, 1, tz=TIMEZONE),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=90),
    default_args=default_args,
    params={
        "extract_mode": Param(
            "incremental",
            type="string",
            enum=["incremental", "full", "since"],
            description="incremental (watermark), full (backfill) or since (needs `since`).",
        ),
        "since": Param(
            None,
            type=["null", "string"],
            pattern=r"^\d{4}-\d{2}-\d{2}$",
            description="YYYY-MM-DD, only for extract_mode=since.",
        ),
    },
    tags=["trm", "pits"],
) as dag:
    extract = PitsCliOperator(
        task_id="extract",
        command=["extract", "trm"],
        env_allow=[*S3_ENV, *SODA_ENV],
        secret_env=[*S3_SECRETS, *SODA_SECRETS],
        param_args="trm_extract",
        execution_timeout=timedelta(minutes=15),
    )
    normalize = PitsCliOperator(
        task_id="normalize",
        command=["normalize", "trm"],
        env_allow=S3_ENV,
        secret_env=S3_SECRETS,
        execution_timeout=timedelta(minutes=10),
    )
    load = PitsCliOperator(
        task_id="load",
        command=["load", "fx-rate"],
        env_allow=[*S3_ENV, *WAREHOUSE_ENV, "PITS_PG_LOADER_PASSWORD"],
        secret_env=[*S3_SECRETS, "PITS_PG_LOADER_PASSWORD"],
        pool=POOL,
        execution_timeout=timedelta(minutes=10),
    )
    build = PitsCliOperator(
        task_id="build",
        command=["transform", "build", "--select", "tag:fx_rate"],
        env_allow=[*WAREHOUSE_ENV, "PITS_PG_TRANSFORMER_PASSWORD"],
        secret_env=["PITS_PG_TRANSFORMER_PASSWORD"],
        pool=POOL,
        execution_timeout=timedelta(minutes=20),
    )
    # dbt exits 0 on WARN (2 days) and 1 on ERROR (7 days) -> pits exit 1 -> the run fails (P9).
    freshness = PitsCliOperator(
        task_id="freshness",
        command=["transform", "freshness", "--select", "tag:fx_rate"],
        env_allow=[*WAREHOUSE_ENV, "PITS_PG_TRANSFORMER_PASSWORD"],
        secret_env=["PITS_PG_TRANSFORMER_PASSWORD"],
        pool=POOL,
        execution_timeout=timedelta(minutes=5),
    )

    extract >> normalize >> load >> build >> freshness

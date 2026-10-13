"""divipola_snapshot (D129): DIVIPOLA extract -> normalize -> load -> dbt build.

Same shape as runt_fleet_snapshot (D102): a linear chain, every step idempotent, the warehouse
steps serialized through the pool `pits_warehouse` (1 slot; the D90 advisory lock stays the safety
net). DANE rarely changes the table (its rows are from 2025-01-24 although the declared frequency
is semestral), so almost every weekly run ends `unchanged` (extract), `already_present` (normalize)
and `already_loaded` (load): two cheap SODA requests (metadata and count).
There is no freshness task on purpose (D124): any threshold would warn forever.
build is limited to `tag:divipola` (D101): the dimension, the exception seed, the RUNT map and the
enriched fleet mart. The RUNT DAG is not touched: its `tag:vehicle_fleet` build already includes
the seed, the map and the enriched mart. This DAG needs `staging.stg_vehicle_fleet_snapshot` and
`marts.fct_vehicle_fleet_snapshot` to exist (the RUNT pipeline creates them).
`force` (default False) makes extract store a NEW raw batch (about 0.3 MB) even if the source did
not change: a manual recovery tool, never part of the schedule.
"""

from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.sdk import DAG, CronTriggerTimetable, Param

from pits_cli.operator import PitsCliOperator

DAG_ID = "divipola_snapshot"
TIMEZONE = "America/Bogota"  # UTC-5 all year (no DST): 07:00 local == 12:00 UTC
SCHEDULE_CRON = "0 7 * * 1"  # Mondays, outside the daily 10:00 TRM and 11:00 RUNT runs (D106)
POOL = "pits_warehouse"
SELECT = ["--select", "tag:divipola"]

# D104(d): explicit non-secret S3 names (what load_storage_settings reads). NEVER a glob: `S3_*`
# would hand over S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY (admin) if they were ever present.
S3_ENV = ["S3_ENDPOINT_URL", "S3_REGION", "S3_RAW_BUCKET", "S3_NORMALIZED_BUCKET"]
S3_WRITER_ENV = ["PITS_S3_WRITER_ACCESS_KEY_ID", "PITS_S3_WRITER_SECRET_ACCESS_KEY"]
S3_READER_ENV = ["PITS_S3_READER_ACCESS_KEY_ID", "PITS_S3_READER_SECRET_ACCESS_KEY"]
SODA_ENV = ["SODA_*"]
WAREHOUSE_ENV = ["PITS_PG_HOST", "POSTGRES_HOST_PORT", "PITS_WAREHOUSE_DB"]
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
    description="Weekly DANE DIVIPOLA pipeline: raw -> normalized -> landing -> dbt (D129)",
    schedule=CronTriggerTimetable(SCHEDULE_CRON, timezone=TIMEZONE),
    start_date=pendulum.datetime(2026, 10, 1, tz=TIMEZONE),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=60),
    default_args=default_args,
    params={
        "force": Param(
            False,
            type="boolean",
            description="Store a new raw batch even if the source did not change (about 0.3 MB).",
        ),
    },
    tags=["divipola", "pits"],
) as dag:
    extract = PitsCliOperator(
        task_id="extract",
        command=["extract", "divipola"],
        env_allow=[*S3_ENV, *S3_WRITER_ENV, *SODA_ENV],
        secret_env=[*S3_WRITER_ENV, *SODA_SECRETS],
        param_args="divipola_extract",
        execution_timeout=timedelta(minutes=10),
    )
    normalize = PitsCliOperator(
        task_id="normalize",
        command=["normalize", "divipola"],
        env_allow=[*S3_ENV, *S3_WRITER_ENV],
        secret_env=S3_WRITER_ENV,
        execution_timeout=timedelta(minutes=10),
    )
    load = PitsCliOperator(
        task_id="load",
        command=["load", "divipola"],
        env_allow=[*S3_ENV, *S3_READER_ENV, *WAREHOUSE_ENV, "PITS_PG_LOADER_PASSWORD"],
        secret_env=[*S3_READER_ENV, "PITS_PG_LOADER_PASSWORD"],
        pool=POOL,
        execution_timeout=timedelta(minutes=10),
    )
    build = PitsCliOperator(
        task_id="build",
        command=["transform", "build", *SELECT],
        env_allow=[*WAREHOUSE_ENV, "PITS_PG_TRANSFORMER_PASSWORD"],
        secret_env=["PITS_PG_TRANSFORMER_PASSWORD"],
        pool=POOL,
        execution_timeout=timedelta(minutes=15),
    )

    extract >> normalize >> load >> build

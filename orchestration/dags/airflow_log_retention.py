"""airflow_log_retention (D109): daily purge of task logs older than 30 days.

The `airflow_logs` volume grows without bound (every try writes a file); without this DAG the
disk is the failure. The logic lives in pits_cli.log_retention (pure, unit tested); the task
only calls it. No pool: it touches the log volume, not the warehouse.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pendulum
from airflow.sdk import DAG, CronTriggerTimetable, task

from pits_cli.log_retention import LOGS_ROOT, MAX_AGE_DAYS, purge_old_logs

DAG_ID = "airflow_log_retention"
TIMEZONE = "America/Bogota"
SCHEDULE_CRON = "0 3 * * *"

log = logging.getLogger(__name__)

with DAG(
    dag_id=DAG_ID,
    description="Delete Airflow task logs older than 30 days (D109)",
    schedule=CronTriggerTimetable(SCHEDULE_CRON, timezone=TIMEZONE),
    start_date=pendulum.datetime(2026, 10, 1, tz=TIMEZONE),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "data-platform", "retries": 0},
    tags=["maintenance", "pits"],
) as dag:

    @task(task_id="purge_logs", execution_timeout=timedelta(minutes=10), retries=0)
    def purge_logs() -> None:
        result = purge_old_logs(LOGS_ROOT, max_age_days=MAX_AGE_DAYS)
        log.info(
            "log retention: deleted_files=%d freed_bytes=%d removed_dirs=%d",
            result.deleted_files,
            result.freed_bytes,
            result.removed_dirs,
        )

    purge_logs()

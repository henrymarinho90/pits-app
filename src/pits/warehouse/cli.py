"""`pits db` commands.

`pits db migrate` uses the admin profile (POSTGRES_USER/POSTGRES_PASSWORD) to bootstrap roles,
database and schemas, then applies pending SQL migrations. Exit codes: 0 ok, 1 permanent
(configuration, authentication, privileges, migration drift/invalid files), 2 usage error,
3 transient (connection refused/timeout, lock busy, serialization/deadlock; safe to retry).
`pits db init-airflow-meta` (D93) creates the Airflow metadata database and role as the admin.
Nothing sensitive (conninfo, passwords) is ever printed.
"""

from __future__ import annotations

import os
from typing import NoReturn

import typer

from pits.warehouse.airflow_meta import init_airflow_meta, load_metadb_password
from pits.warehouse.errors import WarehouseError, WarehouseTransientError
from pits.warehouse.migrate import MigrateResult, run_migrate
from pits.warehouse.settings import Profile, load_warehouse_settings

db_app = typer.Typer(
    help="Warehouse database administration.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)


@db_app.callback()
def _db() -> None:
    """Warehouse database administration."""


def _fail(message: str, code: int) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=code)


@db_app.command()
def migrate() -> None:
    """Bootstrap roles/database/schemas and apply pending migrations (idempotent)."""
    try:
        settings = load_warehouse_settings(
            os.environ, (Profile.ADMIN, Profile.LOADER, Profile.READER, Profile.TRANSFORMER)
        )
        result: MigrateResult = run_migrate(settings)
    except WarehouseTransientError as exc:
        _fail(str(exc), 3)
    except WarehouseError as exc:
        _fail(str(exc), 1)
    typer.echo(f"database={settings.dbname} applied={result.applied} skipped={result.skipped}")


@db_app.command("init-airflow-meta")
def init_airflow_meta_command() -> None:
    """Create the Airflow metadata database and role (D93; idempotent, run by the admin)."""
    try:
        settings = load_warehouse_settings(os.environ, (Profile.ADMIN,))
        password = load_metadb_password(os.environ)
        result = init_airflow_meta(settings, password)
    except WarehouseTransientError as exc:
        _fail(str(exc), 3)
    except WarehouseError as exc:
        _fail(str(exc), 1)
    typer.echo(f"database={result.database} role={result.role} status={result.status}")

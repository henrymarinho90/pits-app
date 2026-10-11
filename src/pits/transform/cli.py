"""`pits transform {parse,build,freshness}`: run dbt (D88) with the validated environment.

Exit codes: 0 dbt succeeded; 1 permanent (dbt exit 1 or 2, missing project/dbt, configuration,
authentication, privileges); 2 usage error (Typer); 3 transient (preflight connection failure
or another transform run holds the lock; safe to retry).
`parse` needs no credentials and never connects. `build` and `freshness` require
PITS_PG_TRANSFORMER_PASSWORD (so libpq cannot fall back to pgpass), run a preflight as
`pits_transformer` and hold an advisory lock while dbt runs. dbt's own output passes through
untouched; passwords and conninfo are never printed.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from pathlib import Path
from typing import NoReturn

import typer

from pits.transform import runner as rn
from pits.warehouse.errors import WarehouseError, WarehouseTransientError
from pits.warehouse.settings import Profile, WarehouseSettings, load_warehouse_settings

transform_app = typer.Typer(
    help="Run dbt transformations (staging/marts).",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)


def _default_settings(env: Mapping[str, str]) -> WarehouseSettings:
    return load_warehouse_settings(env, (Profile.TRANSFORMER,))


# Replaceable in tests so neither dbt nor Postgres are needed for offline runs.
settings_factory: Callable[[Mapping[str, str]], WarehouseSettings] = _default_settings
session_factory: Callable[[WarehouseSettings], AbstractContextManager[object]] = rn.open_session
dbt_runner: rn.Runner = rn.subprocess_runner
project_dir_factory: Callable[[], Path] = rn.default_project_dir
executable_factory: Callable[[], str] = rn.dbt_executable
environ_factory: Callable[[], Mapping[str, str]] = rn.default_environ


@transform_app.callback()
def _transform() -> None:
    """Run dbt transformations (staging/marts)."""


def _fail(message: str, code: int) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=code)


def _run(command: str, *, needs_database: bool) -> None:
    environ = environ_factory()
    try:
        project_dir = project_dir_factory()
        rn.check_project(project_dir)
        argv = rn.build_argv(command, project_dir, executable_factory())
        if not needs_database:
            code = dbt_runner(argv, rn.child_env(environ))
        else:
            settings = settings_factory(environ)
            with session_factory(settings):
                code = dbt_runner(argv, rn.child_env(environ, settings))
    except WarehouseTransientError as exc:
        _fail(str(exc), 3)
    except WarehouseError as exc:
        _fail(str(exc), 1)
    if code != 0:
        _fail(f"dbt {command} failed (dbt exit code {code})", rn.exit_code_for(code))


@transform_app.command()
def parse() -> None:
    """Parse the dbt project (offline: no credentials, no connection)."""
    _run("parse", needs_database=False)


@transform_app.command()
def build() -> None:
    """Run dbt build (models and tests) as pits_transformer."""
    _run("build", needs_database=True)


@transform_app.command()
def freshness() -> None:
    """Run dbt source freshness as pits_transformer."""
    _run("freshness", needs_database=True)

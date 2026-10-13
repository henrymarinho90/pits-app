"""Building blocks of `pits transform` (D88): paths, dbt argv, child environment, session lock.

The wrapper never imports dbt: it runs the dbt executable of the CURRENT environment as a
subprocess (dbt's Python API is not a stable contract and would load dbt in this process).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

import psycopg

from pits.warehouse.connection import check_environment, connect
from pits.warehouse.errors import (
    WarehouseConfigError,
    WarehouseError,
    WarehouseTransientError,
    to_warehouse_error,
)
from pits.warehouse.locks import TRANSFORM_LOCK_KEY as TRANSFORM_LOCK_KEY
from pits.warehouse.locks import WAREHOUSE_LOCK_KEY
from pits.warehouse.settings import Profile, WarehouseSettings

# Subprocess runner: (argv, env) -> dbt exit code. Replaceable in tests.
Runner = Callable[[Sequence[str], Mapping[str, str]], int]

_DROP_PREFIXES = ("PG", "DBT_", "PITS_PG_", "POSTGRES_")


def default_project_dir() -> Path:
    """`<repo>/transform`, resolved from this file (src/pits/transform/runner.py)."""
    return Path(__file__).resolve().parents[3] / "transform"


def check_project(project_dir: Path) -> None:
    if not (project_dir / "dbt_project.yml").is_file():
        raise WarehouseConfigError(
            f"dbt project not found: {project_dir / 'dbt_project.yml'} is missing "
            "(`pits transform` must run from a source checkout of the repository)"
        )


def dbt_executable() -> str:
    """The `dbt` script installed next to the running interpreter (same venv/lock).

    Chosen over PATH lookup so a different dbt (global install, other version) can never be
    picked up: the one pinned in uv.lock is the only valid one.
    """
    bin_dir = Path(sys.executable).parent
    for name in ("dbt.exe", "dbt"):
        candidate = bin_dir / name
        if candidate.is_file():
            return str(candidate)
    raise WarehouseConfigError(
        f"dbt executable not found next to {bin_dir}; run `uv sync` (group transform)"
    )


SELECT_PATTERN = re.compile(r"^tag:[a-z_]+$")


def validate_select(value: str) -> str:
    """D101: only `tag:<name>` selectors reach dbt (no paths, graph operators or exclusions)."""
    if not SELECT_PATTERN.fullmatch(value):
        raise ValueError(f"invalid selector {value!r}: expected tag:<name> (lowercase letters, _)")
    return value


def build_argv(
    command: str, project_dir: Path, executable: str, select: str | None = None
) -> list[str]:
    sub = {"parse": ["parse"], "build": ["build"], "freshness": ["source", "freshness"]}[command]
    argv = [executable, *sub, "--project-dir", str(project_dir), "--profiles-dir", str(project_dir)]
    if select is not None:
        argv += ["--select", validate_select(select)]
    return argv


def child_env(
    parent: Mapping[str, str], settings: WarehouseSettings | None = None
) -> dict[str, str]:
    """Environment for dbt: no PG*/DBT_*/PITS_PG_*/POSTGRES_* inherited, telemetry off.

    With `settings` (build/freshness) every connection variable read by transform/profiles.yml
    (host, port, database, user, password) is injected from the validated settings, so dbt
    connects exactly as the preflight did. `parse` gets none: profiles.yml uses its defaults.
    """
    env = {k: v for k, v in parent.items() if not k.upper().startswith(_DROP_PREFIXES)}
    env["DO_NOT_TRACK"] = "1"
    env["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "False"
    if settings is not None:
        user, password = settings.credentials(Profile.TRANSFORMER)
        env["PITS_PG_TRANSFORMER_USER"] = user
        env["PITS_PG_TRANSFORMER_PASSWORD"] = password
        env["PITS_WAREHOUSE_DB"] = settings.dbname
        env["PITS_PG_HOST"] = settings.host
        env["POSTGRES_HOST_PORT"] = str(settings.port)
    return env


def subprocess_runner(argv: Sequence[str], env: Mapping[str, str]) -> int:
    """Run dbt inheriting stdout/stderr (its output passes through untouched)."""
    try:
        return subprocess.run(list(argv), env=dict(env), check=False).returncode
    except OSError as exc:
        raise WarehouseConfigError(f"could not start dbt ({type(exc).__name__})") from None


@contextmanager
def open_session(settings: WarehouseSettings) -> Iterator[psycopg.Connection]:
    """Preflight + exclusive run lock: connect as transformer (PG17, expected DB) and hold a
    session advisory lock for the whole dbt run. Busy lock -> WarehouseTransientError."""
    check_environment()
    conn = connect(
        settings, Profile.TRANSFORMER, autocommit=True, application_name="pits-transform"
    )
    try:
        failure: WarehouseError | None = None
        locked = False
        try:
            row = conn.execute("SELECT pg_try_advisory_lock(%s)", (WAREHOUSE_LOCK_KEY,)).fetchone()
            locked = bool(row and row[0])
        except psycopg.Error as exc:
            failure = to_warehouse_error(exc, "transform lock")
        if failure is not None:
            raise failure
        if not locked:
            raise WarehouseTransientError("Another pits transform run holds the lock")
        try:
            yield conn
        finally:
            try:
                conn.execute("SELECT pg_advisory_unlock(%s)", (WAREHOUSE_LOCK_KEY,))
            except psycopg.Error:
                pass  # closing the session releases the lock anyway; never mask dbt's result
    finally:
        conn.close()


def exit_code_for(dbt_code: int) -> int:
    """dbt: 0 ok, 1 handled failure, 2 unhandled error -> pits 1; anything else non-zero too."""
    return 0 if dbt_code == 0 else 1


def default_environ() -> Mapping[str, str]:
    return os.environ

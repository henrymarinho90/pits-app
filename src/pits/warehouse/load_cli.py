"""`pits load fx-rate` (D82) and `pits load vehicle-fleet` (D99): committed normalized artifacts
-> `landing.fx_rate` / `landing.vehicle_fleet_snapshot`.

Exit codes: 0 loaded or already_loaded; 1 permanent (configuration, manifest/hash mismatch,
constraint violation, verification failure, drift without --repair, artifact older than the
loaded one, missing migrations/privileges, authentication failure); 2 usage error (Typer,
including a --fingerprint that is not 64 lowercase hex); 3 transient (S3 or Postgres failure
worth retrying: connection refused, lock busy, 55P03, 40001, 40P01, 57P01, 57P03).
Only the loader credentials are needed (PITS_PG_LOADER_PASSWORD). Nothing sensitive (conninfo,
passwords) is ever printed: errors are printed with str(exc) only, never with a traceback.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from typing import NoReturn

import typer
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError

from pits import __version__
from pits.ingestion.raw_store import RawStore, S3RawStore
from pits.normalized.fleet_reader import PUBLICATION_RE
from pits.storage.client import build_s3_client
from pits.storage.settings import StorageConfigError, StorageSettings, load_storage_settings
from pits.warehouse.errors import WarehouseError, WarehouseTransientError
from pits.warehouse.fx_rate_load import (
    FxRateWarehouse,
    LoadResult,
    load_fx_rate,
    open_warehouse,
)
from pits.warehouse.settings import Profile, WarehouseSettings, load_warehouse_settings
from pits.warehouse.vehicle_fleet_load import (
    FleetLoadResult,
    FleetWarehouse,
    load_vehicle_fleet,
    open_fleet_warehouse,
)

load_app = typer.Typer(
    help="Load normalized artifacts into the warehouse.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)

_FINGERPRINT_RE = re.compile(r"[0-9a-f]{64}")


def _default_settings(env: Mapping[str, str]) -> WarehouseSettings:
    return load_warehouse_settings(env, (Profile.LOADER,))


# Replaceable in tests so neither S3 nor Postgres roles are needed for offline runs.
client_factory: Callable[[StorageSettings], BaseClient] = build_s3_client
store_factory: Callable[[BaseClient, str], RawStore] = S3RawStore
settings_factory: Callable[[Mapping[str, str]], WarehouseSettings] = _default_settings
warehouse_factory: Callable[[WarehouseSettings], AbstractContextManager[FxRateWarehouse]] = (
    open_warehouse
)
fleet_warehouse_factory: Callable[[WarehouseSettings], AbstractContextManager[FleetWarehouse]] = (
    open_fleet_warehouse
)


@load_app.callback()
def _load() -> None:
    """Load normalized artifacts into the warehouse."""


def _fail(message: str, code: int) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=code)


def _check_fingerprint(value: str | None) -> str | None:
    if value is not None and not _FINGERPRINT_RE.fullmatch(value):
        raise typer.BadParameter("must be 64 lowercase hex characters (sha256)")
    return value


def _check_publication(value: str | None) -> str | None:
    if value is not None and not PUBLICATION_RE.fullmatch(value):
        raise typer.BadParameter("must be YYYY-MM (year 2000-2099, month 01-12)")
    return value


def _format_fleet(result: FleetLoadResult, normalized_bucket: str) -> str:
    return (
        f"outcome={result.outcome.value} publication={result.publication} "
        f"load_id={result.load_id} fingerprint={result.fingerprint} rows={result.rows} "
        f"inserted={result.inserted} updated={result.updated} deleted={result.deleted} "
        f"manifest=s3://{normalized_bucket}/{result.manifest_key}"
    )


def _format(result: LoadResult, normalized_bucket: str) -> str:
    return (
        f"outcome={result.outcome.value} load_id={result.load_id} "
        f"fingerprint={result.fingerprint} rows={result.rows} inserted={result.inserted} "
        f"updated={result.updated} deleted={result.deleted} "
        f"coverage={result.coverage_from.isoformat()}..{result.coverage_to.isoformat()} "
        f"manifest=s3://{normalized_bucket}/{result.manifest_key}"
    )


@load_app.command("fx-rate")
def fx_rate(
    fingerprint: str | None = typer.Option(
        None,
        "--fingerprint",
        callback=_check_fingerprint,
        help="Force this normalized artifact (sha256 hex) instead of the latest one.",
    ),
    repair: bool = typer.Option(
        False,
        "--repair",
        help="Re-apply the artifact when the warehouse drifted from the loaded one.",
    ),
) -> None:
    """Load the latest committed fx_rate artifact into landing.fx_rate (idempotent)."""
    try:
        storage = load_storage_settings(os.environ, "reader")
        settings = settings_factory(os.environ)
    except (StorageConfigError, WarehouseError) as exc:
        _fail(str(exc), 1)

    try:
        client = client_factory(storage)
        store = store_factory(client, storage.normalized_bucket)
    except BotoCoreError as exc:
        _fail(f"storage client error ({type(exc).__name__})", 1)

    try:
        with warehouse_factory(settings) as warehouse:
            result = load_fx_rate(
                store,
                warehouse,
                storage.raw_bucket,
                loader_version=__version__,
                fingerprint=fingerprint,
                repair=repair,
            )
    except WarehouseTransientError as exc:
        _fail(str(exc), 3)
    except WarehouseError as exc:
        _fail(str(exc), 1)
    typer.echo(_format(result, storage.normalized_bucket))


@load_app.command("vehicle-fleet")
def vehicle_fleet(
    publication: str | None = typer.Option(
        None,
        "--publication",
        callback=_check_publication,
        help="Load only this publication (YYYY-MM) instead of every committed one.",
    ),
    fingerprint: str | None = typer.Option(
        None,
        "--fingerprint",
        callback=_check_fingerprint,
        help="Force this normalized artifact (sha256 hex) instead of the latest one.",
    ),
    repair: bool = typer.Option(
        False,
        "--repair",
        help="Re-apply the artifact when the warehouse drifted from the loaded one.",
    ),
) -> None:
    """Load the latest committed vehicle_fleet_snapshot of each publication (idempotent).

    One transaction per publication, ascending; a failure leaves the earlier ones loaded.
    """
    try:
        storage = load_storage_settings(os.environ, "reader")
        settings = settings_factory(os.environ)
    except (StorageConfigError, WarehouseError) as exc:
        _fail(str(exc), 1)

    try:
        client = client_factory(storage)
        store = store_factory(client, storage.normalized_bucket)
    except BotoCoreError as exc:
        _fail(f"storage client error ({type(exc).__name__})", 1)

    try:
        with fleet_warehouse_factory(settings) as warehouse:
            # One line per publication, printed as soon as its transaction is committed.
            for result in load_vehicle_fleet(
                store,
                warehouse,
                storage.raw_bucket,
                loader_version=__version__,
                publication=publication,
                fingerprint=fingerprint,
                repair=repair,
            ):
                typer.echo(_format_fleet(result, storage.normalized_bucket))
    except WarehouseTransientError as exc:
        _fail(str(exc), 3)
    except WarehouseError as exc:
        _fail(str(exc), 1)

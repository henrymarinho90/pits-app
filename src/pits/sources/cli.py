"""`pits extract` commands: SODA sources -> raw layer.

Exit codes: 0 committed, 1 permanent error or bad configuration, 2 usage error (including a
`--since` that would leave a gap), 3 transient error (safe to retry later).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import NoReturn

import typer
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError

from pits import __version__
from pits.ingestion.raw_store import RawStore, S3RawStore
from pits.sources.extract_common import ExtractPermanentError, ExtractTransientError
from pits.sources.runt.extract import extract_runt
from pits.sources.soda.client import SodaClient
from pits.sources.soda.settings import SodaConfigError, SodaSettings, load_soda_settings
from pits.sources.trm.extract import ExtractUsageError, extract_trm
from pits.storage.client import build_s3_client
from pits.storage.settings import StorageConfigError, StorageSettings, load_storage_settings

extract_app = typer.Typer(
    help="Extract external sources into the raw layer.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)

# Replaceable in tests so neither a real S3 endpoint nor the real SODA API is needed.
client_factory: Callable[[StorageSettings], BaseClient] = build_s3_client
store_factory: Callable[[BaseClient, str], RawStore] = S3RawStore
soda_factory: Callable[[SodaSettings], SodaClient] = SodaClient


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_batch_id() -> str:
    return str(uuid.uuid4())


# Replaceable in tests for deterministic timestamps and batch ids.
clock: Callable[[], datetime] = _utc_now
batch_id_factory: Callable[[], str] = _new_batch_id


def _fail(message: str, code: int) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=code)


def _parse_since(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is None or parsed.isoformat() != value:
        _fail("--since must be a date in YYYY-MM-DD format", 2)
    return parsed


def _date_or_none(value: date | None) -> str:
    return "none" if value is None else value.isoformat()


@extract_app.command()
def trm(
    full: bool = typer.Option(False, "--full", help="Reload the whole dataset (backfill)."),
    since: str | None = typer.Option(
        None, "--since", metavar="YYYY-MM-DD", help="Reload from this date, inclusive."
    ),
) -> None:
    """Extract the TRM into a new raw batch (default: incremental from the watermark)."""
    if full and since is not None:
        _fail("--full and --since are mutually exclusive", 2)
    since_date = _parse_since(since)
    mode = "full" if full else "since" if since_date else "incremental"

    try:
        soda_settings = load_soda_settings(os.environ)
        storage_settings = load_storage_settings(os.environ, "writer")
    except (SodaConfigError, StorageConfigError) as exc:
        _fail(str(exc), 1)

    try:
        store = store_factory(client_factory(storage_settings), storage_settings.raw_bucket)
    except BotoCoreError as exc:
        _fail(f"storage client error ({type(exc).__name__})", 1)
    try:
        with soda_factory(soda_settings) as soda:
            result = extract_trm(
                soda,
                store,
                mode=mode,
                since=since_date,
                now=clock,
                new_batch_id=batch_id_factory,
                extractor_version=__version__,
            )
    except ExtractUsageError as exc:
        _fail(str(exc), 2)
    except ExtractTransientError as exc:
        _fail(str(exc), 3)
    except ExtractPermanentError as exc:
        _fail(str(exc), 1)

    m = result.manifest
    typer.echo(
        f"batch_id={m.batch_id} mode={m.watermark.mode} rows={m.row_count} files={len(m.files)} "
        f"watermark_from={_date_or_none(m.watermark.from_exclusive)} "
        f"watermark_to={_date_or_none(m.watermark.to_observed)} "
        f"manifest=s3://{storage_settings.raw_bucket}/{result.manifest_key}"
    )


@extract_app.command()
def runt(
    force: bool = typer.Option(
        False, "--force", help="Create a new batch even if rowsUpdatedAt is unchanged."
    ),
) -> None:
    """Extract the RUNT fleet snapshot (always the full dataset) into a new raw batch."""
    try:
        soda_settings = load_soda_settings(os.environ)
        storage_settings = load_storage_settings(os.environ, "writer")
    except (SodaConfigError, StorageConfigError) as exc:
        _fail(str(exc), 1)

    try:
        store = store_factory(client_factory(storage_settings), storage_settings.raw_bucket)
    except BotoCoreError as exc:
        _fail(f"storage client error ({type(exc).__name__})", 1)
    try:
        with soda_factory(soda_settings) as soda:
            result = extract_runt(
                soda,
                store,
                force=force,
                now=clock,
                new_batch_id=batch_id_factory,
                extractor_version=__version__,
            )
    except ExtractTransientError as exc:
        _fail(str(exc), 3)
    except ExtractPermanentError as exc:
        _fail(str(exc), 1)

    m = result.manifest
    typer.echo(
        f"outcome={result.outcome} batch_id={m.batch_id} publication={result.publication} "
        f"rows={m.row_count} files={len(m.files)} "
        f"manifest=s3://{storage_settings.raw_bucket}/{result.manifest_key}"
    )

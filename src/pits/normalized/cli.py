"""`pits normalize` commands: raw layer -> normalized layer (replay; never calls SODA).

Exit codes: 0 created or already_present, 1 permanent error / bad configuration / missing or
unversioned bucket, 2 usage error, 3 transient error (incl. 5xx or connection failure while
checking the bucket; safe to retry later).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import NoReturn

import typer
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError

from pits.ingestion.raw_store import RawStore, S3RawStore
from pits.sources.normalize_common import NormalizePermanentError, NormalizeTransientError
from pits.sources.runt.normalize import normalize_runt
from pits.sources.trm.normalize import normalize_trm
from pits.storage.client import build_s3_client
from pits.storage.raw_bucket import RawBucketError, RawBucketTransientError, verify_versioned_bucket
from pits.storage.settings import StorageConfigError, StorageSettings, load_storage_settings

normalize_app = typer.Typer(
    help="Normalize raw sources into the normalized layer.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)

# Replaceable in tests so no real S3 endpoint is needed.
client_factory: Callable[[StorageSettings], BaseClient] = build_s3_client
store_factory: Callable[[BaseClient, str], RawStore] = S3RawStore


def _fail(message: str, code: int) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=code)


def _connect() -> tuple[StorageSettings, RawStore, RawStore]:
    """Load settings, build both stores and verify the normalized bucket (exit 1/3 on failure)."""
    try:
        settings = load_storage_settings(os.environ)
    except StorageConfigError as exc:
        _fail(str(exc), 1)

    try:
        client = client_factory(settings)
        raw_store = store_factory(client, settings.raw_bucket)
        normalized_store = store_factory(client, settings.normalized_bucket)
    except BotoCoreError as exc:
        _fail(f"storage client error ({type(exc).__name__})", 1)
    try:
        verify_versioned_bucket(client, settings.normalized_bucket)
    except RawBucketTransientError as exc:
        _fail(str(exc), 3)
    except RawBucketError as exc:
        _fail(str(exc), 1)
    except BotoCoreError as exc:
        _fail(f"storage endpoint error ({type(exc).__name__})", 3)
    return settings, raw_store, normalized_store


@normalize_app.command()
def trm(
    warn_range_days: int = typer.Option(
        5,
        "--warn-range-days",
        min=1,
        help="Warn on stderr if a source validity range is longer than this many days.",
    ),
) -> None:
    """Replay the committed raw TRM batches into the fx_rate CSV + manifest (idempotent)."""
    settings, raw_store, normalized_store = _connect()

    try:
        result = normalize_trm(raw_store, normalized_store, raw_bucket=settings.raw_bucket)
    except NormalizeTransientError as exc:
        _fail(str(exc), 3)
    except NormalizePermanentError as exc:
        _fail(str(exc), 1)

    if result.max_range_days > warn_range_days:
        typer.echo(
            f"warning: longest source validity range is {result.max_range_days} days "
            f"(> {warn_range_days}); review the source before trusting the expansion",
            err=True,
        )
    bucket = settings.normalized_bucket
    typer.echo(
        f"outcome={result.outcome.value} fingerprint={result.fingerprint} "
        f"inputs={result.inputs} baseline={result.baseline_batch_id} rows={result.rows} "
        f"coverage={result.coverage_from.isoformat()}..{result.coverage_to.isoformat()} "
        f"csv=s3://{bucket}/{result.csv_key} manifest=s3://{bucket}/{result.manifest_key}"
    )


@normalize_app.command()
def runt() -> None:
    """Replay the committed raw RUNT batches into one vehicle_fleet_snapshot per publication."""
    settings, raw_store, normalized_store = _connect()
    bucket = settings.normalized_bucket
    try:
        # One line per publication, printed as soon as its artifact is committed.
        for result in normalize_runt(raw_store, normalized_store, raw_bucket=settings.raw_bucket):
            typer.echo(
                f"outcome={result.outcome.value} publication={result.publication} "
                f"fingerprint={result.fingerprint} inputs={result.inputs} "
                f"batch={result.batch_id} rows={result.rows} parts={result.parts} "
                f"manifest=s3://{bucket}/{result.manifest_key}"
            )
    except NormalizeTransientError as exc:
        _fail(str(exc), 3)
    except NormalizePermanentError as exc:
        _fail(str(exc), 1)

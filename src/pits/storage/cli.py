"""`pits storage` commands."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import NoReturn

import typer
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError

from pits.storage.client import build_s3_client
from pits.storage.orphans import (
    MAX_UNEXPECTED_SAMPLES,
    NORMALIZED_LAYOUT,
    RAW_LAYOUT,
    Orphan,
    OrphansError,
    OrphansTransientError,
    escape_key,
    format_timestamp,
    scan_bucket,
)
from pits.storage.raw_bucket import RawBucketError, ensure_versioned_bucket
from pits.storage.settings import StorageConfigError, StorageSettings, load_storage_settings

storage_app = typer.Typer(
    help="Object storage commands.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)

# Replaceable in tests so no real S3 endpoint is needed.
client_factory: Callable[[StorageSettings], BaseClient] = build_s3_client


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


def _flag(value: bool) -> str:
    return "true" if value else "false"


@storage_app.command()
def init() -> None:
    """Create the raw and normalized buckets if missing; make sure versioning is Enabled."""
    try:
        settings = load_storage_settings(os.environ, identity="admin")
        client = client_factory(settings)
        for bucket in (settings.raw_bucket, settings.normalized_bucket):
            result = ensure_versioned_bucket(client, bucket)
            typer.echo(
                f"bucket={result.bucket} created={_flag(result.created)} "
                f"versioning=Enabled changed={_flag(result.versioning_changed)}"
            )
    except (StorageConfigError, RawBucketError) as exc:
        _fail(str(exc))
    except BotoCoreError as exc:
        _fail(f"storage endpoint error ({type(exc).__name__})")


def _echo_orphan(orphan: Orphan) -> None:
    typer.echo(
        f"orphan bucket={orphan.bucket} prefix={escape_key(orphan.prefix)} "
        f"objects={orphan.objects} bytes={orphan.bytes} newest={format_timestamp(orphan.newest)}"
    )


@storage_app.command()
def orphans() -> None:
    """Read-only inventory of prefixes without manifest.json (D107).

    Exit 0 inventory, 1 config or access denied, 3 transient storage error. Never writes.
    """
    try:
        settings = load_storage_settings(os.environ, identity="reader")
        client = client_factory(settings)
        for bucket, layout in (
            (settings.raw_bucket, RAW_LAYOUT),
            (settings.normalized_bucket, NORMALIZED_LAYOUT),
        ):
            report = scan_bucket(client, bucket, layout, _echo_orphan)
            for key in report.unexpected_samples:
                typer.echo(f"unexpected bucket={bucket} key={escape_key(key)}")
            if report.unexpected > MAX_UNEXPECTED_SAMPLES:
                typer.echo(
                    f"unexpected bucket={bucket} more={report.unexpected - MAX_UNEXPECTED_SAMPLES}"
                )
            typer.echo(
                f"bucket={bucket} groups={report.groups} committed={report.committed} "
                f"orphans={report.orphans} orphan_bytes={report.orphan_bytes} "
                f"unexpected={report.unexpected}"
            )
    except StorageConfigError as exc:
        _fail(str(exc))
    except OrphansTransientError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    except OrphansError as exc:
        _fail(str(exc))
    except BotoCoreError as exc:
        typer.echo(f"error: storage endpoint error ({type(exc).__name__})", err=True)
        raise typer.Exit(code=3) from exc

"""`pits storage` commands."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import NoReturn

import typer
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError

from pits.storage.client import build_s3_client
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
        settings = load_storage_settings(os.environ, "admin")
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

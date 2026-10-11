"""Idempotent provisioning of the raw bucket (versioned, no Object Lock; D61)."""

from __future__ import annotations

from dataclasses import dataclass

from botocore.client import BaseClient
from botocore.exceptions import ClientError

_MISSING_CODES = {"404", "NoSuchBucket", "NotFound"}
_DENIED_CODES = {"403", "Forbidden", "AccessDenied"}


class RawBucketError(RuntimeError):
    """Raised when the raw bucket cannot be provisioned in the expected state."""


@dataclass(frozen=True)
class EnsureResult:
    """Outcome of ensure_raw_bucket."""

    bucket: str
    created: bool
    versioning_changed: bool


def _code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


def _bucket_exists(client: BaseClient, bucket: str) -> bool:
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        code = _code(exc)
        if code in _MISSING_CODES:
            return False
        if code in _DENIED_CODES:
            raise RawBucketError(
                f"Access denied to bucket '{bucket}': it may belong to another owner "
                "or the credentials lack permission"
            ) from exc
        raise RawBucketError(f"head_bucket failed for '{bucket}': {code or exc}") from exc
    return True


def _create_bucket(client: BaseClient, bucket: str) -> bool:
    """Create the bucket; return False if it already exists and is owned by us (race)."""
    kwargs: dict[str, object] = {"Bucket": bucket}
    region = client.meta.region_name
    if region and region != "us-east-1":
        kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
    try:
        client.create_bucket(**kwargs)
    except ClientError as exc:
        if _code(exc) == "BucketAlreadyOwnedByYou":
            return False
        raise RawBucketError(f"create_bucket failed for '{bucket}': {_code(exc) or exc}") from exc
    return True


def _versioning_status(client: BaseClient, bucket: str) -> str | None:
    try:
        return client.get_bucket_versioning(Bucket=bucket).get("Status")
    except ClientError as exc:
        raise RawBucketError(
            f"get_bucket_versioning failed for '{bucket}': {_code(exc) or exc}"
        ) from exc


def ensure_raw_bucket(client: BaseClient, bucket: str) -> EnsureResult:
    """Make sure `bucket` exists with versioning Enabled; safe to re-run."""
    created = False
    if not _bucket_exists(client, bucket):
        created = _create_bucket(client, bucket)

    status = _versioning_status(client, bucket)
    if status == "Enabled":
        return EnsureResult(bucket=bucket, created=created, versioning_changed=False)
    if status == "Suspended":
        raise RawBucketError(
            f"Versioning on '{bucket}' is Suspended; refusing to change it automatically"
        )

    try:
        client.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
    except ClientError as exc:
        raise RawBucketError(
            f"put_bucket_versioning failed for '{bucket}': {_code(exc) or exc}"
        ) from exc

    final = _versioning_status(client, bucket)
    if final != "Enabled":
        raise RawBucketError(f"Versioning on '{bucket}' is '{final}' after enabling it")
    return EnsureResult(bucket=bucket, created=created, versioning_changed=True)

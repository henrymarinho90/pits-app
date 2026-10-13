"""Idempotent provisioning of versioned buckets (raw D61, normalized D74; no Object Lock)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from botocore.client import BaseClient
from botocore.exceptions import ClientError

_MISSING_CODES = {"404", "NoSuchBucket", "NotFound"}
_DENIED_CODES = {"403", "Forbidden", "AccessDenied"}
_TRANSIENT_CODES = {"SlowDown", "RequestTimeout", "InternalError", "ServiceUnavailable"}
_NO_POLICY_CODES = {"NoSuchBucketPolicy"}


class RawBucketError(RuntimeError):
    """Raised when a platform bucket (raw or normalized) is not in the expected state."""


@dataclass(frozen=True)
class EnsureResult:
    """Outcome of ensure_versioned_bucket."""

    bucket: str
    created: bool
    versioning_changed: bool


class RawBucketTransientError(RawBucketError):
    """The storage answered with a transient failure (5xx, throttling): retry later."""


def _is_transient(exc: ClientError) -> bool:
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return _code(exc) in _TRANSIENT_CODES or (isinstance(status, int) and status >= 500)


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
        error = RawBucketTransientError if _is_transient(exc) else RawBucketError
        raise error(f"head_bucket failed for '{bucket}': {code or exc}") from exc
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
        error = RawBucketTransientError if _is_transient(exc) else RawBucketError
        raise error(f"get_bucket_versioning failed for '{bucket}': {_code(exc) or exc}") from exc


def ensure_versioned_bucket(client: BaseClient, bucket: str) -> EnsureResult:
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


def ensure_raw_bucket(client: BaseClient, bucket: str) -> EnsureResult:
    """Raw-bucket name for ensure_versioned_bucket (same behavior)."""
    return ensure_versioned_bucket(client, bucket)


def verify_versioned_bucket(client: BaseClient, bucket: str) -> None:
    """Check only (never create or change): bucket exists and versioning is Enabled."""
    if not _bucket_exists(client, bucket):
        raise RawBucketError(f"Bucket '{bucket}' does not exist; run `pits storage init` first")
    status = _versioning_status(client, bucket)
    if status != "Enabled":
        shown = status or "not enabled"
        raise RawBucketError(
            f"Versioning on '{bucket}' is {shown}; run `pits storage init` "
            "(a Suspended bucket must be fixed manually)"
        )


# --- Write-once bucket policy (D104(c)) --------------------------------------------------------
# Deny for every principal on DeleteObject, DeleteObjectVersion and PutBucketVersioning (admin
# included). KNOWN LIMITATION (SeaweedFS 4.48, verified on a probe): the admin identity bypasses
# the policy in DeleteObjects (multi-delete, POST ?delete); adding s3:DeleteObjects, s3:Delete* or
# s3:* to the Deny does not change that. Writer and reader are blocked there (per-key
# AccessDenied), and neither has PutBucketPolicy, so they cannot lift the policy. Protection
# against a deliberate admin action is therefore partial.
DENY_DELETE_SID = "DenyObjectDelete"
DENY_VERSIONING_SID = "DenyVersioningChange"


def write_once_policy(bucket: str) -> dict[str, Any]:
    """Bucket policy that denies object deletion and versioning changes to everyone."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": DENY_DELETE_SID,
                "Effect": "Deny",
                "Principal": "*",
                "Action": ["s3:DeleteObject", "s3:DeleteObjectVersion"],
                "Resource": f"arn:aws:s3:::{bucket}/*",
            },
            {
                "Sid": DENY_VERSIONING_SID,
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:PutBucketVersioning",
                "Resource": f"arn:aws:s3:::{bucket}",
            },
        ],
    }


def _as_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return sorted(str(item) for item in value)
    return [repr(value)]


_LIST_KEYS = ("Action", "NotAction", "Resource", "NotResource")


def _canonical(policy: object) -> list[str] | None:
    """Order- and shape-insensitive form of EVERY statement key (Condition, NotPrincipal, ...).

    Only Action/Resource-style values are normalized (SeaweedFS rewrites 1-item lists as
    strings); Principal is compared as returned ({"AWS": "*"} is NOT folded into "*": the
    server stores it verbatim, verified on a probe).
    """
    if not isinstance(policy, dict) or not isinstance(policy.get("Statement"), list):
        return None
    out: list[str] = []
    for st in policy["Statement"]:
        if not isinstance(st, dict):
            return None
        norm = {k: (_as_list(v) if k in _LIST_KEYS else v) for k, v in st.items()}
        out.append(json.dumps(norm, sort_keys=True))
    return sorted(out)


def _read_policy(client: BaseClient, bucket: str) -> object | None:
    """Current policy document, or None if the bucket has none."""
    try:
        text = client.get_bucket_policy(Bucket=bucket)["Policy"]
    except ClientError as exc:
        if _code(exc) in _NO_POLICY_CODES:
            return None
        error = RawBucketTransientError if _is_transient(exc) else RawBucketError
        raise error(f"get_bucket_policy failed for '{bucket}': {_code(exc) or exc}") from exc
    try:
        return json.loads(text)
    except (TypeError, ValueError) as exc:
        raise RawBucketError(f"Bucket policy of '{bucket}' is not valid JSON") from exc


def ensure_write_once_policy(client: BaseClient, bucket: str) -> bool:
    """Apply the write-once policy and verify it by reading it back; return True if (re)written.

    Idempotent: an equivalent existing policy is left untouched. Any other policy on the bucket
    is replaced (this bucket's policy belongs to the platform). Needs the admin identity.
    """
    desired = write_once_policy(bucket)
    expected = _canonical(desired)
    if _canonical(_read_policy(client, bucket)) == expected:
        return False
    try:
        client.put_bucket_policy(
            Bucket=bucket, Policy=json.dumps(desired, sort_keys=True, separators=(",", ":"))
        )
    except ClientError as exc:
        raise RawBucketError(
            f"put_bucket_policy failed for '{bucket}': {_code(exc) or exc}"
        ) from exc
    if _canonical(_read_policy(client, bucket)) != expected:
        raise RawBucketError(
            f"Bucket policy of '{bucket}' does not match the write-once policy after applying it"
        )
    return True

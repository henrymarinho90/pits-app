"""Storage settings loaded from environment variables."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlparse

DEFAULT_REGION = "us-east-1"
RESERVED_BUCKET_PREFIX = "pits-contract-"  # reserved for contract tests (D61)

_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_FORBIDDEN_PREFIXES = ("xn--", "sthree-", "amzn-s3-demo-")
_FORBIDDEN_SUFFIXES = ("-s3alias", "--ol-s3", ".mrap", "--x-s3", "--table-s3")
_IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


class StorageConfigError(ValueError):
    """Raised when the storage configuration is missing or invalid."""


@dataclass(frozen=True)
class StorageSettings:
    """Connection settings for the S3-compatible object store."""

    endpoint_url: str
    access_key_id: str
    secret_access_key: str = field(repr=False)
    region: str
    raw_bucket: str


def validate_bucket_name(name: str) -> None:
    """Validate an S3 bucket name and reject the reserved contract-test prefix."""
    if (
        not _BUCKET_RE.match(name)
        or ".." in name
        or _IPV4_RE.match(name)
        or name.startswith(_FORBIDDEN_PREFIXES)
        or name.endswith(_FORBIDDEN_SUFFIXES)
    ):
        raise StorageConfigError(
            "S3_RAW_BUCKET is not a valid S3 bucket name "
            "(3-63 chars of a-z, 0-9, '-', '.'; alphanumeric ends; not an IP address; "
            "no reserved AWS prefix/suffix)"
        )
    if name.startswith(RESERVED_BUCKET_PREFIX):
        raise StorageConfigError(f"S3_RAW_BUCKET must not start with '{RESERVED_BUCKET_PREFIX}'")


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise StorageConfigError(f"Missing required environment variable: {name}")
    return value


def load_storage_settings(env: Mapping[str, str]) -> StorageSettings:
    """Build StorageSettings from `env`; error messages never include values."""
    endpoint_url = _required(env, "S3_ENDPOINT_URL")
    access_key_id = _required(env, "S3_ACCESS_KEY_ID")
    secret_access_key = _required(env, "S3_SECRET_ACCESS_KEY")
    raw_bucket = _required(env, "S3_RAW_BUCKET")
    region = env.get("S3_REGION", "").strip() or DEFAULT_REGION

    parsed = urlparse(endpoint_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise StorageConfigError("S3_ENDPOINT_URL must be an http(s) URL with a host")
    if parsed.username is not None or parsed.password is not None:
        raise StorageConfigError("S3_ENDPOINT_URL must not embed credentials")
    validate_bucket_name(raw_bucket)

    return StorageSettings(
        endpoint_url=endpoint_url,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        region=region,
        raw_bucket=raw_bucket,
    )

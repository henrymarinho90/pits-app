"""Storage settings loaded from environment variables."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlparse

DEFAULT_REGION = "us-east-1"
DEFAULT_NORMALIZED_BUCKET = "pits-normalized"  # D74
RESERVED_BUCKET_PREFIX = "pits-contract-"  # reserved for contract tests (D61)

_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_FORBIDDEN_PREFIXES = ("xn--", "sthree-", "amzn-s3-demo-")
_FORBIDDEN_SUFFIXES = ("-s3alias", "--ol-s3", ".mrap", "--x-s3", "--table-s3")
_ACCESS_KEY_RE = re.compile(r"^[A-Za-z0-9]{16,128}$")
_SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


Identity = Literal["admin", "writer", "reader"]

# D104(b): one S3 identity per role; each CLI asks for its own and never falls back to admin.
_IDENTITY_VARS: dict[str, tuple[str, str]] = {
    "admin": ("S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"),
    "writer": ("PITS_S3_WRITER_ACCESS_KEY_ID", "PITS_S3_WRITER_SECRET_ACCESS_KEY"),
    "reader": ("PITS_S3_READER_ACCESS_KEY_ID", "PITS_S3_READER_SECRET_ACCESS_KEY"),
}


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
    normalized_bucket: str = DEFAULT_NORMALIZED_BUCKET


def validate_bucket_name(name: str, variable: str = "S3_RAW_BUCKET") -> None:
    """Validate an S3 bucket name and reject the reserved contract-test prefix."""
    if (
        not _BUCKET_RE.match(name)
        or ".." in name
        or _IPV4_RE.match(name)
        or name.startswith(_FORBIDDEN_PREFIXES)
        or name.endswith(_FORBIDDEN_SUFFIXES)
    ):
        raise StorageConfigError(
            f"{variable} is not a valid S3 bucket name "
            "(3-63 chars of a-z, 0-9, '-', '.'; alphanumeric ends; not an IP address; "
            "no reserved AWS prefix/suffix)"
        )
    if name.startswith(RESERVED_BUCKET_PREFIX):
        raise StorageConfigError(f"{variable} must not start with '{RESERVED_BUCKET_PREFIX}'")


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise StorageConfigError(f"Missing required environment variable: {name}")
    return value


def _identity_credentials(env: Mapping[str, str], identity: str) -> tuple[str, str]:
    """Return (access_key, secret) for `identity`; errors name variables, never values."""
    if identity not in _IDENTITY_VARS:
        raise StorageConfigError(f"Unknown storage identity: {identity!r}")
    key_var, secret_var = _IDENTITY_VARS[identity]
    access_key_id = _required(env, key_var)
    secret_access_key = _required(env, secret_var)
    if identity != "admin":
        # The admin credential predates the format and is not validated (D104(b)).
        if not _ACCESS_KEY_RE.match(access_key_id):
            raise StorageConfigError(f"{key_var} must be 16-128 alphanumeric characters")
        if not _SECRET_RE.match(secret_access_key):
            raise StorageConfigError(f"{secret_var} must be 32-128 characters of A-Z a-z 0-9 _ -")
        for other, (other_key_var, _) in _IDENTITY_VARS.items():
            if other != identity and env.get(other_key_var, "").strip() == access_key_id:
                raise StorageConfigError(
                    f"{key_var} must differ from {other_key_var} (one access key per identity)"
                )
    return access_key_id, secret_access_key


def load_storage_settings(env: Mapping[str, str], identity: Identity = "admin") -> StorageSettings:
    """Build StorageSettings from `env` for one S3 identity; errors never include values."""
    endpoint_url = _required(env, "S3_ENDPOINT_URL")
    access_key_id, secret_access_key = _identity_credentials(env, identity)
    raw_bucket = _required(env, "S3_RAW_BUCKET")
    region = env.get("S3_REGION", "").strip() or DEFAULT_REGION

    parsed = urlparse(endpoint_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise StorageConfigError("S3_ENDPOINT_URL must be an http(s) URL with a host")
    if parsed.username is not None or parsed.password is not None:
        raise StorageConfigError("S3_ENDPOINT_URL must not embed credentials")
    validate_bucket_name(raw_bucket)
    normalized_bucket = env.get("S3_NORMALIZED_BUCKET", "").strip() or DEFAULT_NORMALIZED_BUCKET
    validate_bucket_name(normalized_bucket, "S3_NORMALIZED_BUCKET")
    if normalized_bucket == raw_bucket:
        raise StorageConfigError("S3_NORMALIZED_BUCKET must differ from S3_RAW_BUCKET")

    return StorageSettings(
        endpoint_url=endpoint_url,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        region=region,
        raw_bucket=raw_bucket,
        normalized_bucket=normalized_bucket,
    )

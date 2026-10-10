"""Pure helpers for the S3 contract tests (importable without a live endpoint)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import boto3
from botocore.client import BaseClient
from botocore.config import Config

ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost"})
MIN_LARGE_MB = 100
DEFAULT_LARGE_MB = 128
DEFAULT_REGION = "us-east-1"


class SettingsError(ValueError):
    """Invalid or missing contract-test configuration."""


@dataclass(frozen=True)
class S3Settings:
    endpoint_url: str
    access_key_id: str
    secret_access_key: str
    region: str
    large_mb: int


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise SettingsError(f"{name} is required for contract tests (see .env.example)")
    return value


def load_settings(env: Mapping[str, str]) -> S3Settings:
    endpoint = _require(env, "S3_ENDPOINT_URL")
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SettingsError(f"S3_ENDPOINT_URL must be a full http(s) URL, got {endpoint!r}")
    if parsed.hostname not in ALLOWED_HOSTS:
        raise SettingsError(
            f"S3_ENDPOINT_URL host {parsed.hostname!r} rejected: contract tests only run "
            f"against {sorted(ALLOWED_HOSTS)}"
        )
    raw_mb = env.get("S3_CONTRACT_LARGE_MB", "").strip() or str(DEFAULT_LARGE_MB)
    try:
        large_mb = int(raw_mb)
    except ValueError:
        raise SettingsError(f"S3_CONTRACT_LARGE_MB must be an integer, got {raw_mb!r}") from None
    if large_mb < MIN_LARGE_MB:
        raise SettingsError(f"S3_CONTRACT_LARGE_MB must be >= {MIN_LARGE_MB}, got {large_mb}")
    return S3Settings(
        endpoint_url=endpoint,
        access_key_id=_require(env, "S3_ACCESS_KEY_ID"),
        secret_access_key=_require(env, "S3_SECRET_ACCESS_KEY"),
        region=env.get("S3_REGION", "").strip() or DEFAULT_REGION,
        large_mb=large_mb,
    )


def build_client(settings: S3Settings, access_key: str, secret_key: str) -> BaseClient:
    """Client with explicit credentials (never from AWS_* env vars)."""
    return boto3.client(
        "s3",
        endpoint_url=settings.endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=settings.region,
        config=Config(
            s3={"addressing_style": "path"},
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=5,
            read_timeout=60,
        ),
    )


def purge_bucket(client: BaseClient, name: str) -> None:
    """Abort multipart uploads, delete all versions and delete markers, then the bucket."""
    for page in client.get_paginator("list_multipart_uploads").paginate(Bucket=name):
        for upload in page.get("Uploads", []):
            client.abort_multipart_upload(
                Bucket=name, Key=upload["Key"], UploadId=upload["UploadId"]
            )
    for page in client.get_paginator("list_object_versions").paginate(Bucket=name):
        items: list[dict[str, Any]] = [*page.get("Versions", []), *page.get("DeleteMarkers", [])]
        for i in range(0, len(items), 1000):
            objects = [
                {"Key": o["Key"], **({"VersionId": o["VersionId"]} if o.get("VersionId") else {})}
                for o in items[i : i + 1000]
            ]
            resp = client.delete_objects(Bucket=name, Delete={"Objects": objects, "Quiet": True})
            errors = resp.get("Errors")
            if errors:
                raise RuntimeError(f"delete_objects failed in {name}: {errors[:3]}")
    client.delete_bucket(Bucket=name)


class BucketFactory:
    """Creates uniquely named buckets and cleans them up at teardown.

    Buckets holding COMPLIANCE-locked objects cannot be purged: call `keep(name)`.
    """

    def __init__(self, client: BaseClient) -> None:
        self._client = client
        self._created: list[str] = []
        self._kept: set[str] = set()

    def __call__(self, object_lock: bool = False) -> str:
        name = f"pits-contract-{uuid.uuid4().hex[:8]}"
        kwargs = {"ObjectLockEnabledForBucket": True} if object_lock else {}
        self._client.create_bucket(Bucket=name, **kwargs)
        self._created.append(name)
        return name

    def keep(self, name: str) -> None:
        self._kept.add(name)

    def cleanup(self) -> list[str]:
        """Purge every non-kept bucket; return one error message per failed bucket."""
        errors: list[str] = []
        for name in self._created:
            if name in self._kept:
                continue
            try:
                purge_bucket(self._client, name)
            except Exception as exc:  # noqa: BLE001
                # Keep going: one stuck bucket must not leak the rest; errors are reported.
                errors.append(f"{name}: {exc!r}")
        return errors

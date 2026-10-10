"""Fixtures for S3 contract tests against a live, local S3 endpoint.

Run with: uv run --env-file .env pytest -m contract -q
"""

from __future__ import annotations

import os
import warnings
from collections.abc import Callable, Iterator

import pytest
from botocore.client import BaseClient
from s3_helpers import (
    BucketFactory,
    S3Settings,
    SettingsError,
    build_client,
    load_settings,
    purge_contract_buckets,
)


@pytest.fixture(scope="session")
def s3_settings() -> S3Settings:
    try:
        return load_settings(os.environ)
    except SettingsError as exc:
        pytest.fail(str(exc), pytrace=False)


@pytest.fixture(scope="session")
def make_client(s3_settings: S3Settings) -> Callable[[str, str], BaseClient]:
    return lambda access_key, secret_key: build_client(s3_settings, access_key, secret_key)


@pytest.fixture(scope="session")
def s3(s3_settings: S3Settings) -> BaseClient:
    client = build_client(s3_settings, s3_settings.access_key_id, s3_settings.secret_access_key)
    # Best-effort: purge leftovers of previous runs (COMPLIANCE buckets whose retention has
    # expired). Buckets with active retention fail with AccessDenied; they only raise a warning.
    for message in purge_contract_buckets(client):
        warnings.warn(
            f"leftover contract bucket not purged (retention still active?): {message[:200]}",
            stacklevel=2,
        )
    return client


@pytest.fixture
def make_bucket(s3: BaseClient) -> Iterator[BucketFactory]:
    factory = BucketFactory(s3)
    yield factory
    errors = factory.cleanup()
    if errors:
        pytest.fail("bucket cleanup failed: " + "; ".join(errors), pytrace=False)


@pytest.fixture
def bucket(make_bucket: BucketFactory) -> str:
    return make_bucket()

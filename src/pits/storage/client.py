"""S3 client factory."""

from __future__ import annotations

import boto3
from botocore.client import BaseClient
from botocore.config import Config

from pits.storage.settings import StorageSettings


def build_s3_client(settings: StorageSettings) -> BaseClient:
    """Create a path-style S3 client with standard retries and bounded timeouts."""
    return boto3.client(
        "s3",
        endpoint_url=settings.endpoint_url,
        aws_access_key_id=settings.access_key_id,
        aws_secret_access_key=settings.secret_access_key,
        region_name=settings.region,
        config=Config(
            s3={"addressing_style": "path"},
            retries={"mode": "standard", "max_attempts": 3},  # 3 retries -> 4 attempts total
            connect_timeout=5,
            read_timeout=60,
        ),
    )

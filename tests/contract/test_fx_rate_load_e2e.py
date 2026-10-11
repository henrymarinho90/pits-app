"""E2E contract: fake SODA -> raw (real S3) -> normalize -> load into Postgres -> checksum.

Needs BOTH a live S3 endpoint (S3_*, buckets pits-contract-*) and the local Postgres 17
(POSTGRES_USER/POSTGRES_PASSWORD; fixtures of tests/pg: per-test database and roles).
Run: uv run --env-file ../pits-app/.env pytest -m "contract and pg" -q
"""

from __future__ import annotations

from datetime import date

import pytest
from botocore.client import BaseClient
from pg_support import pg_settings  # noqa: F401  (fixture)
from s3_helpers import BucketFactory
from soda_fake import contiguous_rows, extract_batch

from pits.ingestion.manifest import sha256_hex
from pits.ingestion.raw_store import S3RawStore
from pits.normalized.manifest import NormalizedManifest
from pits.sources.trm.normalize import normalize_trm
from pits.warehouse.connection import connect
from pits.warehouse.fx_rate_load import Outcome, load_fx_rate, open_warehouse, reconstruct_digest
from pits.warehouse.migrate import run_migrate
from pits.warehouse.settings import Profile

pytestmark = [pytest.mark.contract, pytest.mark.pg]

B1 = "0b6f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a10"
DAY = date(2026, 10, 10)
ROWS = 34  # contiguous_rows(): 10 ranges of 3 days + 1 of 4 days


def _versioned(s3: BaseClient, make_bucket: BucketFactory) -> str:
    name = make_bucket()
    s3.put_bucket_versioning(Bucket=name, VersioningConfiguration={"Status": "Enabled"})
    return name


def test_raw_to_normalized_to_warehouse_with_checksum(
    s3: BaseClient,
    make_bucket: BucketFactory,
    pg_settings,  # noqa: F811
) -> None:
    raw_bucket, norm_bucket = _versioned(s3, make_bucket), _versioned(s3, make_bucket)
    raw, norm = S3RawStore(s3, raw_bucket), S3RawStore(s3, norm_bucket)
    extract_batch(raw, contiguous_rows(), batch_id=B1, day=DAY)
    normalized = normalize_trm(raw, norm, raw_bucket=raw_bucket)
    assert normalized.rows == ROWS

    run_migrate(pg_settings)

    with open_warehouse(pg_settings) as warehouse:
        first = load_fx_rate(norm, warehouse, raw_bucket, loader_version="e2e")
        second = load_fx_rate(norm, warehouse, raw_bucket, loader_version="e2e")

    assert first.outcome is Outcome.LOADED and first.inserted == ROWS
    assert (first.updated, first.deleted) == (0, 0)
    assert first.fingerprint == normalized.fingerprint
    assert second.outcome is Outcome.ALREADY_LOADED and second.load_id == first.load_id

    # Checksum: the table rebuilt in order must equal the CSV object stored in S3.
    csv = s3.get_object(Bucket=norm_bucket, Key=normalized.csv_key)["Body"].read()
    manifest = NormalizedManifest.from_json(
        s3.get_object(Bucket=norm_bucket, Key=normalized.manifest_key)["Body"].read()
    )
    admin = connect(pg_settings, Profile.ADMIN, autocommit=True)
    try:
        rows = admin.execute(
            "SELECT rate_date, currency_from, currency_to, rate, source_reference "
            "FROM landing.fx_rate ORDER BY rate_date, currency_from, currency_to"
        ).fetchall()
        runs = admin.execute(
            "SELECT count(*), max(input_fingerprint), max(csv_sha256) FROM ops.load_run"
        ).fetchone()
    finally:
        admin.close()
    sha256, size = reconstruct_digest(rows)
    assert (sha256, size) == (sha256_hex(csv), len(csv))
    assert (sha256, size) == (manifest.output.sha256, manifest.output.size_bytes)
    assert runs == (1, normalized.fingerprint, sha256)

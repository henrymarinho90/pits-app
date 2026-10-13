"""E2E contract: fake RUNT raw (real S3) -> normalize -> load into Postgres -> checksum (D99).

Needs BOTH a live S3 endpoint (S3_*, buckets pits-contract-*) and the local Postgres 17
(POSTGRES_USER/POSTGRES_PASSWORD; fixtures of tests/pg: per-test database and roles).
Run: uv run --env-file ../pits-app/.env pytest -m "contract and pg" -q -k vehicle_fleet
"""

from __future__ import annotations

from datetime import date

import pytest
from botocore.client import BaseClient
from pg_support import pg_settings  # noqa: F401  (fixture)
from runt_support import B1, B2, big_rows, put_runt_batch
from s3_helpers import BucketFactory

from pits.ingestion.manifest import sha256_hex
from pits.ingestion.raw_store import S3RawStore
from pits.normalized.fleet_manifest import FleetManifest
from pits.sources.runt.normalize import normalize_runt
from pits.warehouse.connection import connect
from pits.warehouse.migrate import run_migrate
from pits.warehouse.settings import Profile
from pits.warehouse.vehicle_fleet_load import (
    Outcome,
    load_vehicle_fleet,
    open_fleet_warehouse,
    reconstruct_digest,
)

pytestmark = [pytest.mark.contract, pytest.mark.pg]

DAY = date(2026, 10, 12)
ROWS_SEP, ROWS_OCT = 45, 30_000  # 2026-10 has two parts (MAX_PART_ROWS = 20_000)


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
    put_runt_batch(raw, B1, DAY, big_rows(ROWS_SEP, month=9), month=9, page_size=10)
    put_runt_batch(raw, B2, DAY, big_rows(ROWS_OCT), month=10, page_size=5000)
    normalized = {r.publication: r for r in normalize_runt(raw, norm, raw_bucket=raw_bucket)}
    assert [normalized[p].rows for p in ("2026-09", "2026-10")] == [ROWS_SEP, ROWS_OCT]
    assert normalized["2026-10"].parts == 2

    run_migrate(pg_settings)

    with open_fleet_warehouse(pg_settings) as warehouse:
        first = list(load_vehicle_fleet(norm, warehouse, raw_bucket, loader_version="e2e"))
        second = list(load_vehicle_fleet(norm, warehouse, raw_bucket, loader_version="e2e"))

    assert [r.outcome for r in first] == [Outcome.LOADED] * 2
    assert [(r.publication, r.inserted, r.deleted) for r in first] == [
        ("2026-09", ROWS_SEP, 0),
        ("2026-10", ROWS_OCT, 0),
    ]
    assert [r.outcome for r in second] == [Outcome.ALREADY_LOADED] * 2
    assert [r.load_id for r in second] == [r.load_id for r in first]

    admin = connect(pg_settings, Profile.ADMIN, autocommit=True)
    try:
        for publication, year_month in (("2026-09", (2026, 9)), ("2026-10", (2026, 10))):
            manifest = FleetManifest.from_json(
                s3.get_object(Bucket=norm_bucket, Key=normalized[publication].manifest_key)[
                    "Body"
                ].read()
            )
            rows = admin.execute(
                "SELECT publication_year, publication_month, department_name, municipality_name, "
                "service_name, vehicle_status, vehicle_class, registration_year, vehicle_count, "
                "source_reference FROM landing.vehicle_fleet_snapshot "
                "WHERE publication_year = %s AND publication_month = %s "
                'ORDER BY department_name COLLATE "C", municipality_name COLLATE "C", '
                'service_name COLLATE "C", vehicle_status COLLATE "C", '
                'vehicle_class COLLATE "C", registration_year',
                year_month,
            ).fetchall()
            sha256, size = reconstruct_digest(rows)
            # The logical CSV (header once + every part's rows) straight from the S3 objects.
            logical = b""
            for index, part in enumerate(manifest.parts):
                body = s3.get_object(Bucket=norm_bucket, Key=part.key)["Body"].read()
                logical += body if index == 0 else body.split(b"\n", 1)[1]
            assert (sha256, size) == (sha256_hex(logical), len(logical))
            assert (sha256, size) == (manifest.content_sha256, manifest.content_size_bytes)
            assert sum(r[8] for r in rows) == manifest.vehicle_count_total
        runs = admin.execute(
            "SELECT count(*), count(DISTINCT input_fingerprint) FROM ops.load_run"
        ).fetchone()
        assert runs == (2, 2)
    finally:
        admin.close()

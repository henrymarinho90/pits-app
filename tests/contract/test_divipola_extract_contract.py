"""Contract: DIVIPOLA extractor against a live, local S3 endpoint (SODA simulated, no network).

Run with: uv run --env-file ../pits-app/.env pytest -m contract -q -k divipola
Tests the storage side (D62/D65/D122): layout, manifest written last, sha256 fidelity, unchanged
without writes, --force new batch, and no manifest when the dataset changes mid-run.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from botocore.client import BaseClient
from divipola_support import B1, B2, FakeDivipola, rows
from s3_helpers import BucketFactory

from pits.ingestion.manifest import Manifest, find_latest_committed, sha256_hex
from pits.ingestion.raw_store import PutOutcome, S3RawStore
from pits.sources.divipola.contract import DATASET_ID, SOURCE_SYSTEM
from pits.sources.divipola.extract import DivipolaExtractResult, extract_divipola
from pits.sources.extract_common import ExtractTransientError

pytestmark = pytest.mark.contract

PAGE_SIZE = 3


class RecordingStore:
    """S3RawStore wrapper that records the order of successful writes."""

    def __init__(self, inner: S3RawStore) -> None:
        self._inner = inner
        self.written: list[str] = []

    def put_once(self, key: str, body: bytes, content_type: str) -> PutOutcome:
        outcome = self._inner.put_once(key, body, content_type)
        if outcome is PutOutcome.CREATED:
            self.written.append(key)
        return outcome

    def list_prefixes(self, prefix: str) -> list[str]:
        return self._inner.list_prefixes(prefix)

    def get(self, key: str) -> bytes:
        return self._inner.get(key)


class Clock:
    def __init__(self, day: date) -> None:
        self.t = datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.t += timedelta(seconds=1)
        return self.t


@pytest.fixture
def bucket(s3: BaseClient, make_bucket: BucketFactory) -> str:
    name = make_bucket()
    s3.put_bucket_versioning(Bucket=name, VersioningConfiguration={"Status": "Enabled"})
    return name


def _run(
    store: RecordingStore, fake: FakeDivipola, batch_id: str, day: date, *, force: bool = False
) -> DivipolaExtractResult:
    return extract_divipola(
        fake.client(),
        store,
        force=force,
        now=Clock(day),
        new_batch_id=lambda: batch_id,
        extractor_version="contract-test",
        page_size=PAGE_SIZE,
    )


def test_batch_layout_manifest_last_and_sha256(s3: BaseClient, bucket: str) -> None:
    store = RecordingStore(S3RawStore(s3, bucket))
    result = _run(store, FakeDivipola(rows(7)), B1, date(2026, 10, 13))
    manifest = result.manifest

    prefix = f"{SOURCE_SYSTEM}/extraction_date=2026-10-13/batch_id={B1}/"
    expected = [f"{prefix}payload-{i:05d}.json" for i in range(3)] + [f"{prefix}manifest.json"]
    assert result.outcome == "committed"
    assert store.written == expected  # manifest is the last write (commit marker)
    assert [f.row_count for f in manifest.files] == [3, 3, 1]
    versions = s3.list_object_versions(Bucket=bucket).get("Versions", [])
    assert sorted(v["Key"] for v in versions) == sorted(expected)
    for entry in manifest.files:
        body = s3.get_object(Bucket=bucket, Key=entry.key)["Body"].read()
        assert sha256_hex(body) == entry.sha256 and len(body) == entry.size_bytes
        assert len(json.loads(body)) == entry.row_count
    stored = Manifest.from_json(
        s3.get_object(Bucket=bucket, Key=f"{prefix}manifest.json")["Body"].read()
    )
    assert stored == manifest
    assert stored.watermark.to_observed == date(2025, 1, 24)


def test_unchanged_does_not_write_and_force_creates_batch(s3: BaseClient, bucket: str) -> None:
    store = RecordingStore(S3RawStore(s3, bucket))
    first = _run(store, FakeDivipola(rows(5)), B1, date(2026, 10, 13))
    written = list(store.written)

    second = _run(store, FakeDivipola(rows(5)), B2, date(2026, 10, 14))
    assert second.outcome == "unchanged"
    assert second.manifest.batch_id == B1 and second.manifest_key == first.manifest_key
    assert store.written == written

    forced = _run(store, FakeDivipola(rows(5)), B2, date(2026, 10, 14), force=True)
    assert forced.outcome == "committed" and forced.manifest.batch_id == B2
    latest = find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID)
    assert latest is not None and latest.batch_id == B2


def test_dataset_replaced_mid_run_leaves_no_manifest(s3: BaseClient, bucket: str) -> None:
    store = RecordingStore(S3RawStore(s3, bucket))
    fake = FakeDivipola(rows(5))
    fake.bump_after_page_calls = 1
    with pytest.raises(ExtractTransientError):
        _run(store, fake, B1, date(2026, 10, 13))
    assert store.written
    assert not any(k.endswith("manifest.json") for k in store.written)
    assert find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID) is None

"""Contract: TRM extractor against a live, local S3 endpoint (SODA simulated).

Run with: uv run --env-file .env pytest -m contract -q
Tests the storage side (D62/D65/D66): key layout, manifest written last, sha256 fidelity,
batch superseding, write-once conflicts (real 412) and list_prefixes fidelity vs the fake.
The SODA API is simulated with httpx.MockTransport: the contract is about the storage.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from botocore.client import BaseClient
from s3_helpers import BucketFactory

from pits.ingestion.manifest import Manifest, find_latest_committed, sha256_hex
from pits.ingestion.raw_store import (
    MemoryRawStore,
    RawObjectExistsError,
    RawObjectNotFoundError,
    S3RawStore,
)
from pits.sources.soda.client import SodaClient
from pits.sources.soda.settings import SodaSettings
from pits.sources.trm.contract import DATASET_ID, SOURCE_SYSTEM
from pits.sources.trm.extract import ExtractPermanentError, ExtractTransientError, Mode, extract_trm

pytestmark = pytest.mark.contract

B1 = "0b6f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a10"
B2 = "1c7a7d2f-4d2b-4a1f-8b62-3e5d7a9fab21"
START = date(2026, 1, 1)
COLUMNS = [
    {"fieldName": "valor", "dataTypeName": "number"},
    {"fieldName": "unidad", "dataTypeName": "text"},
    {"fieldName": "vigenciadesde", "dataTypeName": "calendar_date"},
    {"fieldName": "vigenciahasta", "dataTypeName": "calendar_date"},
]
PAGE_SIZE = 3


def _rows(n: int) -> list[dict[str, str]]:
    out = []
    for i in range(n):
        stamp = f"{(START + timedelta(days=i)).isoformat()}T00:00:00.000"
        out.append(
            {
                "valor": f"{3900 + i}.5",
                "unidad": "COP",
                "vigenciadesde": stamp,
                "vigenciahasta": stamp,
            }
        )
    return out


def _soda(rows: list[dict[str, str]], bump_on_recheck: bool = False) -> SodaClient:
    meta_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/views/"):
            nonlocal meta_calls
            meta_calls += 1
            updated = 101 if bump_on_recheck and meta_calls > 1 else 100
            return httpx.Response(200, json={"rowsUpdatedAt": updated, "columns": COLUMNS})
        params = request.url.params
        selected = rows
        match = re.fullmatch(
            r"vigenciadesde > '(\d{4}-\d{2}-\d{2})T00:00:00\.000'", params.get("$where", "")
        )
        if match:
            selected = [r for r in rows if r["vigenciadesde"][:10] > match.group(1)]
        offset, limit = int(params["$offset"]), int(params["$limit"])
        return httpx.Response(200, content=json.dumps(selected[offset : offset + limit]).encode())

    return SodaClient(
        SodaSettings(base_url="https://example.test", app_token=None),
        transport=httpx.MockTransport(handler),
        sleep=lambda s: None,
        jitter=lambda: 0.0,
    )


class RecordingStore:
    """S3RawStore wrapper that records the order of successful writes."""

    def __init__(self, inner: S3RawStore) -> None:
        self._inner = inner
        self.written: list[str] = []

    def put_once(self, key: str, body: bytes, content_type: str) -> None:
        self._inner.put_once(key, body, content_type)
        self.written.append(key)

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
    store: RecordingStore, rows: list[dict[str, str]], batch_id: str, mode: Mode, day: date
) -> Manifest:
    result = extract_trm(
        _soda(rows),
        store,
        mode=mode,
        since=None,
        now=Clock(day),
        new_batch_id=lambda: batch_id,
        extractor_version="contract-test",
        page_size=PAGE_SIZE,
    )
    return result.manifest


def test_batch_layout_manifest_last_and_sha256(s3: BaseClient, bucket: str) -> None:
    store = RecordingStore(S3RawStore(s3, bucket))
    manifest = _run(store, _rows(7), B1, "full", date(2026, 10, 10))

    prefix = f"{SOURCE_SYSTEM}/extraction_date=2026-10-10/batch_id={B1}/"
    expected = [f"{prefix}payload-{i:05d}.json" for i in range(3)] + [f"{prefix}manifest.json"]
    assert store.written == expected  # manifest is the last write (commit marker)
    assert manifest.row_count == 7
    assert [f.row_count for f in manifest.files] == [3, 3, 1]

    # Exactly these objects, one version each, nothing under another prefix.
    versions = s3.list_object_versions(Bucket=bucket).get("Versions", [])
    assert sorted(v["Key"] for v in versions) == sorted(expected)
    assert all(v["IsLatest"] for v in versions)

    for entry in manifest.files:
        body = s3.get_object(Bucket=bucket, Key=entry.key)["Body"].read()
        assert sha256_hex(body) == entry.sha256
        assert len(body) == entry.size_bytes
        assert len(json.loads(body)) == entry.row_count
    stored = Manifest.from_json(
        s3.get_object(Bucket=bucket, Key=f"{prefix}manifest.json")["Body"].read()
    )
    assert stored == manifest


def test_second_run_new_batch_becomes_latest(s3: BaseClient, bucket: str) -> None:
    store = RecordingStore(S3RawStore(s3, bucket))
    first = _run(store, _rows(5), B1, "incremental", date(2026, 10, 10))
    assert first.watermark.mode == "full"  # no previous batch: backfill
    latest_first = find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID)
    assert latest_first is not None and latest_first.batch_id == B1

    second = _run(store, _rows(8), B2, "incremental", date(2026, 10, 11))
    assert second.batch_id == B2 != B1
    assert second.watermark.mode == "incremental"
    assert second.watermark.from_exclusive == first.watermark.to_observed
    assert second.row_count == 3
    latest = find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID)
    assert latest is not None and latest.batch_id == B2


def test_forced_repeated_batch_id_fails_with_real_412(s3: BaseClient, bucket: str) -> None:
    store = RecordingStore(S3RawStore(s3, bucket))
    first = _run(store, _rows(4), B1, "full", date(2026, 10, 10))
    before = s3.get_object(Bucket=bucket, Key=first.files[0].key)["Body"].read()

    with pytest.raises(ExtractPermanentError) as exc_info:
        _run(store, _rows(4), B1, "full", date(2026, 10, 10))
    assert isinstance(exc_info.value.__cause__, RawObjectExistsError)
    # Existing objects are untouched and still a single version.
    assert s3.get_object(Bucket=bucket, Key=first.files[0].key)["Body"].read() == before
    versions = s3.list_object_versions(Bucket=bucket).get("Versions", [])
    assert len(versions) == len(first.files) + 1


def test_list_prefixes_matches_memory_fake(s3: BaseClient, bucket: str) -> None:
    real = RecordingStore(S3RawStore(s3, bucket))
    fake = MemoryRawStore()
    for day, batch_id in ((date(2026, 10, 10), B1), (date(2026, 10, 11), B2)):
        _run(real, _rows(5), batch_id, "full", day)
        extract_trm(
            _soda(_rows(5)),
            fake,
            mode="full",
            since=None,
            now=Clock(day),
            new_batch_id=lambda b=batch_id: b,
            extractor_version="contract-test",
            page_size=PAGE_SIZE,
        )

    root = f"{SOURCE_SYSTEM}/"
    partitions = real.list_prefixes(root)
    assert partitions == [
        f"{root}extraction_date=2026-10-10/",
        f"{root}extraction_date=2026-10-11/",
    ]
    assert partitions == fake.list_prefixes(root)
    assert real.list_prefixes(partitions[0]) == [f"{partitions[0]}batch_id={B1}/"]
    for p in partitions:
        assert real.list_prefixes(p) == fake.list_prefixes(p)
    assert real.list_prefixes("nonexistent/") == fake.list_prefixes("nonexistent/") == []


def test_orphan_batch_without_manifest_is_ignored(s3: BaseClient, bucket: str) -> None:
    store = S3RawStore(s3, bucket)
    first = _run(RecordingStore(store), _rows(4), B1, "full", date(2026, 10, 10))
    orphan = f"{SOURCE_SYSTEM}/extraction_date=2026-10-11/batch_id={B2}/payload-00000.json"
    store.put_once(orphan, b"[]", "application/json")

    latest = find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID)
    assert latest is not None and latest.batch_id == first.batch_id == B1
    with pytest.raises(RawObjectNotFoundError):
        store.get("nope/missing.json")


def test_dataset_replaced_mid_run_leaves_no_manifest(s3: BaseClient, bucket: str) -> None:
    store = RecordingStore(S3RawStore(s3, bucket))
    with pytest.raises(ExtractTransientError):
        extract_trm(
            _soda(_rows(5), bump_on_recheck=True),
            store,
            mode="full",
            since=None,
            now=Clock(date(2026, 10, 10)),
            new_batch_id=lambda: B1,
            extractor_version="contract-test",
            page_size=PAGE_SIZE,
        )
    assert store.written  # payloads were written
    assert not any(k.endswith("manifest.json") for k in store.written)
    assert find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID) is None

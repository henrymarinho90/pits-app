"""Contract: RUNT extractor against a live, local S3 endpoint (SODA simulated).

Run with: uv run --env-file ../pits-app/.env pytest -m contract -q -k runt
Tests the storage side (D62/D65/D96): layout, manifest written last, sha256 fidelity, unchanged
without writes, --force new batch, and no manifest when the dataset changes mid-run.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from botocore.client import BaseClient
from s3_helpers import BucketFactory

from pits.ingestion.manifest import Manifest, find_latest_committed, sha256_hex
from pits.ingestion.raw_store import PutOutcome, S3RawStore
from pits.sources.extract_common import ExtractTransientError
from pits.sources.runt.contract import DATASET_ID, SOURCE_SYSTEM
from pits.sources.runt.extract import RuntExtractResult, extract_runt
from pits.sources.soda.client import SodaClient
from pits.sources.soda.settings import SodaSettings

pytestmark = pytest.mark.contract

B1 = "0b6f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a10"
B2 = "1c7a7d2f-4d2b-4a1f-8b62-3e5d7a9fab21"
PAGE_SIZE = 3
NAMES = (
    ("nombre_departamento", "text"),
    ("nombre_municipio", "text"),
    ("nombre_servicio", "text"),
    ("estado_del_vehiculo", "text"),
    ("nombre_de_la_clase", "text"),
    ("fecha_de_registro", "number"),
    ("cantidad", "number"),
    ("mes_de_publicacion", "text"),
    ("a_o_de_publicacion", "number"),
)
COLUMNS = [{"fieldName": n, "dataTypeName": t} for n, t in NAMES]


def _rows(n: int) -> list[dict[str, str]]:
    return [
        {
            "nombre_departamento": "CUNDINAMARCA",
            "nombre_municipio": f"MUNI{i}",
            "nombre_servicio": "PARTICULAR",
            "estado_del_vehiculo": "ACTIVO",
            "nombre_de_la_clase": "AUTOMOVIL",
            "fecha_de_registro": "2010",
            "cantidad": str(i + 1),
            "mes_de_publicacion": "OCTUBRE",
            "a_o_de_publicacion": "2026",
        }
        for i in range(n)
    ]


def _soda(rows: list[dict[str, str]], updated_at: int = 100, bump_on_recheck: bool = False):
    meta_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal meta_calls
        if request.url.path.startswith("/api/views/"):
            meta_calls += 1
            value = updated_at + 1 if bump_on_recheck and meta_calls > 1 else updated_at
            return httpx.Response(200, json={"rowsUpdatedAt": value, "columns": COLUMNS})
        params = request.url.params
        if "$group" in params:
            group = {
                "a_o_de_publicacion": "2026",
                "mes_de_publicacion": "OCTUBRE",
                "count": str(len(rows)),
            }
            return httpx.Response(200, json=[group])
        offset, limit = int(params["$offset"]), int(params["$limit"])
        return httpx.Response(200, content=json.dumps(rows[offset : offset + limit]).encode())

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
    store: RecordingStore,
    soda: SodaClient,
    batch_id: str,
    day: date,
    *,
    force: bool = False,
) -> RuntExtractResult:
    return extract_runt(
        soda,
        store,
        force=force,
        now=Clock(day),
        new_batch_id=lambda: batch_id,
        extractor_version="contract-test",
        page_size=PAGE_SIZE,
    )


def test_batch_layout_manifest_last_and_sha256(s3: BaseClient, bucket: str) -> None:
    store = RecordingStore(S3RawStore(s3, bucket))
    result = _run(store, _soda(_rows(7)), B1, date(2026, 10, 12))
    manifest = result.manifest

    prefix = f"{SOURCE_SYSTEM}/extraction_date=2026-10-12/batch_id={B1}/"
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
    assert stored.watermark.to_observed == date(2026, 10, 1)


def test_unchanged_does_not_write_and_force_creates_batch(s3: BaseClient, bucket: str) -> None:
    store = RecordingStore(S3RawStore(s3, bucket))
    first = _run(store, _soda(_rows(5)), B1, date(2026, 10, 12))
    written = list(store.written)

    second = _run(store, _soda(_rows(5)), B2, date(2026, 10, 13))
    assert second.outcome == "unchanged"
    assert second.manifest.batch_id == B1 and second.manifest_key == first.manifest_key
    assert store.written == written

    forced = _run(store, _soda(_rows(5)), B2, date(2026, 10, 13), force=True)
    assert forced.outcome == "committed" and forced.manifest.batch_id == B2
    latest = find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID)
    assert latest is not None and latest.batch_id == B2


def test_dataset_replaced_mid_run_leaves_no_manifest(s3: BaseClient, bucket: str) -> None:
    store = RecordingStore(S3RawStore(s3, bucket))
    with pytest.raises(ExtractTransientError):
        _run(store, _soda(_rows(5), bump_on_recheck=True), B1, date(2026, 10, 12))
    assert store.written
    assert not any(k.endswith("manifest.json") for k in store.written)
    assert find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID) is None

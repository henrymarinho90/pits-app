"""Shared offline test helpers for tests/ingestion (no test_ prefix: no basename collisions)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from pits.ingestion.manifest import (
    Extractor,
    FileEntry,
    Manifest,
    Query,
    SchemaColumn,
    Watermark,
    manifest_key,
    sha256_hex,
)
from pits.ingestion.raw_store import MemoryRawStore, batch_prefix

SS = "superfinanciera_trm"
DS = "32sa-8pi3"
B1 = "0b6f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a10"
B2 = "1c7a7d2f-4d2b-4a1f-8b62-3e5d7a9fab21"
B3 = "2d8b8e30-5e3c-4b20-9c73-4f6e8bafbc32"


def make_manifest(batch_id=B1, day=date(2026, 10, 10), finished=None, **overrides) -> Manifest:
    prefix = batch_prefix(SS, day, batch_id)
    started = overrides.get("started_at") or datetime(day.year, day.month, day.day, 12, tzinfo=UTC)
    base = {
        "source_system": SS,
        "dataset_id": DS,
        "source_url": "https://www.datos.gov.co/resource/32sa-8pi3.json",
        "license": "CC_40_BY_SA",
        "attribution": "Superintendencia Financiera de Colombia - SUPERFINANCIERA, Bogotá D.C.",
        "batch_id": batch_id,
        "extraction_date": day,
        "started_at": started,
        "finished_at": finished or started + timedelta(seconds=30),
        "extractor": Extractor("pits.sources.trm", "0.1.0"),
        "source_rows_updated_at": 1760054700,
        "app_token_used": False,
        "query": Query(order="vigenciadesde ASC, :id ASC", page_size=1000, where=None),
        "watermark": Watermark("vigenciadesde", "full", None, date(2026, 10, 10)),
        "schema": (SchemaColumn("valor", "number"), SchemaColumn("vigenciadesde", "calendar_date")),
        "row_count": 1500,
        "files": (
            FileEntry(
                prefix + "payload-00000.json", 0, 1000, 120, sha256_hex(b"a"), "application/json"
            ),
            FileEntry(
                prefix + "payload-00001.json", 1000, 500, 60, sha256_hex(b"b"), "application/json"
            ),
        ),
    }
    base.update(overrides)
    return Manifest(**base)


def commit(store: MemoryRawStore, manifest: Manifest) -> None:
    prefix = batch_prefix(manifest.source_system, manifest.extraction_date, manifest.batch_id)
    store.put_once(manifest_key(prefix), manifest.to_json(), "application/json")


def mutated(manifest: Manifest, mutate) -> bytes:
    data = json.loads(manifest.to_json())
    mutate(data)
    return json.dumps(data).encode()


class CountingStore(MemoryRawStore):
    def __init__(self):
        super().__init__()
        self.gets: list[str] = []

    def get(self, key):
        self.gets.append(key)
        return super().get(key)

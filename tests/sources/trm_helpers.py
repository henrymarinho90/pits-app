"""Shared pure-test helpers for the TRM parse/replay tests (no test_ prefix)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from pits.ingestion.manifest import (
    Extractor,
    FileEntry,
    Manifest,
    Query,
    SchemaColumn,
    Watermark,
    sha256_hex,
)
from pits.ingestion.raw_store import batch_prefix
from pits.sources.trm.contract import DATASET_ID, SOURCE_SYSTEM
from pits.sources.trm.parse import TrmRecord

B1 = "0b6f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a10"
B2 = "1c7a7d2f-4d2b-4a1f-8b62-3e5d7a9fab21"
B3 = "2d8b8e30-5e3c-4b20-9c73-4f6e8bafbc32"
B4 = "3e9c9f41-6f4d-4c31-8d84-5a7f9cb0cd43"


def rec(frm: date, to: date | None = None, rate: str = "3900.5", ref: str = "k#row=0"):
    return TrmRecord(frm, to or frm, Decimal(rate), ref)


def day_records(start: date, days: int, rate: str = "3900.5", tag: str = "k") -> list[TrmRecord]:
    """One single-day record per calendar day (weekends included, as the source publishes)."""
    return [rec(start + timedelta(days=i), rate=rate, ref=f"{tag}#row={i}") for i in range(days)]


def make_batch(
    batch_id: str,
    day: date,
    mode: str,
    records: list[TrmRecord],
    *,
    from_exclusive: date | None = None,
    finished_at: datetime | None = None,
) -> Manifest:
    """Manifest with a single placeholder file entry; payloads are served by the test reader."""
    started = datetime(day.year, day.month, day.day, 12, tzinfo=UTC)
    prefix = batch_prefix(SOURCE_SYSTEM, day, batch_id)
    files = (
        (
            FileEntry(
                prefix + "payload-00000.json",
                0,
                len(records),
                1,
                sha256_hex(b"x"),
                "application/json",
            ),
        )
        if records
        else ()
    )
    to_observed = records[-1].valid_from if records else from_exclusive
    return Manifest(
        source_system=SOURCE_SYSTEM,
        dataset_id=DATASET_ID,
        source_url="https://example.test/resource/32sa-8pi3.json",
        license="CC_40_BY_SA",
        attribution="test",
        batch_id=batch_id,
        extraction_date=day,
        started_at=started,
        finished_at=finished_at or started + timedelta(seconds=30),
        extractor=Extractor("pits.sources.trm", "test"),
        source_rows_updated_at=None,
        app_token_used=False,
        query=Query(order="vigenciadesde ASC, :id ASC", page_size=1000, where=None),
        watermark=Watermark("vigenciadesde", mode, from_exclusive, to_observed),
        schema=(SchemaColumn("valor", "number"),),
        row_count=len(records),
        files=files,
    )


class Reader:
    """read_records stand-in: serves records per batch_id."""

    def __init__(self, data: dict[str, list[TrmRecord]]) -> None:
        self.data = data

    def __call__(self, manifest: Manifest) -> list[TrmRecord]:
        return self.data[manifest.batch_id]

"""DIVIPOLA extractor: SODA -> raw batch in the write-once raw store (D122).

The dataset is a small reference table (about 1,100 rows) that DANE rarely changes. Every run
reads it whole: validate the metadata schema, count the rows up front (truncation guard), page
ordered by :id, validate each page and store its bytes untouched, re-check rowsUpdatedAt and the
total, and only then write manifest.json (the commit marker). If the latest committed batch has
the same rowsUpdatedAt nothing is written (outcome=unchanged) unless forced.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pits.ingestion.manifest import (
    Extractor,
    FileEntry,
    Manifest,
    ManifestError,
    Query,
    Watermark,
    find_latest_committed,
    manifest_key,
    sha256_hex,
)
from pits.ingestion.raw_store import (
    RawStore,
    RawStoreError,
    RawStoreTransientError,
    batch_prefix,
)
from pits.sources.divipola.contract import (
    ATTRIBUTION,
    DATASET_ID,
    EXPECTED_SCHEMA,
    LICENSE,
    MAX_PAGE_BYTES,
    ORDER,
    PAGE_SIZE,
    SOURCE_SYSTEM,
    SOURCE_URL,
    WATERMARK_COLUMN,
    RowError,
    validate_row,
)
from pits.sources.extract_common import (
    ExtractPermanentError,
    ExtractTransientError,
    check_metadata,
    parse_rows_updated_at,
)
from pits.sources.soda.client import (
    RawPage,
    SodaClient,
    SodaPermanentError,
    SodaTransientError,
)

EXTRACTOR_NAME = "pits.sources.divipola"
_INT_RE = re.compile(r"[0-9]+")

Outcome = Literal["committed", "unchanged"]


@dataclass(frozen=True)
class DivipolaExtractResult:
    outcome: Outcome
    manifest: Manifest  # for "unchanged": the latest committed batch (nothing was written)
    manifest_key: str

    @property
    def rows_updated(self) -> str:
        """UTC date of the source rowsUpdatedAt of the batch (the watermark)."""
        to_observed = self.manifest.watermark.to_observed
        return "none" if to_observed is None else to_observed.isoformat()


def extract_divipola(
    soda: SodaClient,
    store: RawStore,
    *,
    force: bool,
    now: Callable[[], datetime],
    new_batch_id: Callable[[], str],
    extractor_version: str,
    page_size: int = PAGE_SIZE,
) -> DivipolaExtractResult:
    """Extract DIVIPOLA into one committed raw batch; see module docstring."""
    try:
        return _extract(soda, store, force, now, new_batch_id, extractor_version, page_size)
    except (SodaTransientError, RawStoreTransientError) as exc:
        raise ExtractTransientError(str(exc)) from exc
    except (SodaPermanentError, RawStoreError, ManifestError) as exc:
        raise ExtractPermanentError(str(exc)) from exc


def _read_total(soda: SodaClient) -> int:
    page = soda.get_page(DATASET_ID, {"$select": "count(*)"})
    if len(page.rows) != 1 or set(page.rows[0]) != {"count"}:
        raise ExtractPermanentError("Count query returned an unexpected shape")
    count = page.rows[0]["count"]
    if not isinstance(count, str) or not _INT_RE.fullmatch(count) or int(count) < 1:
        raise ExtractPermanentError("Row count is not a positive integer string")
    return int(count)


def _validate_page(page: RawPage, offset: int) -> None:
    for i, row in enumerate(page.rows):
        try:
            validate_row(row)
        except RowError as exc:
            raise ExtractPermanentError(exc.at(f"row {offset + i}")) from None


def _extract(
    soda: SodaClient,
    store: RawStore,
    force: bool,
    now: Callable[[], datetime],
    new_batch_id: Callable[[], str],
    extractor_version: str,
    page_size: int,
) -> DivipolaExtractResult:
    started_at = now()
    if started_at.tzinfo is None:
        raise ValueError("now() must return a timezone-aware datetime")
    extraction_date = started_at.astimezone(UTC).date()

    rows_updated_at = check_metadata(soda, DATASET_ID, EXPECTED_SCHEMA)
    total = _read_total(soda)

    if not force:
        previous = find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID)
        if previous is not None and previous.source_rows_updated_at == rows_updated_at:
            key = manifest_key(
                batch_prefix(SOURCE_SYSTEM, previous.extraction_date, previous.batch_id)
            )
            return DivipolaExtractResult("unchanged", previous, key)

    try:
        updated_date = datetime.fromtimestamp(rows_updated_at, UTC).date()
    except (OverflowError, OSError, ValueError):
        raise ExtractPermanentError("Metadata rowsUpdatedAt is not a valid timestamp") from None

    batch_id = new_batch_id()  # only when a batch will actually be written
    prefix = batch_prefix(SOURCE_SYSTEM, extraction_date, batch_id)
    files: list[FileEntry] = []
    offset = 0
    while True:
        page = soda.get_page(DATASET_ID, {"$order": ORDER, "$limit": page_size, "$offset": offset})
        if not page.rows:
            break  # an empty page is never written
        _validate_page(page, offset)
        if len(page.body) > MAX_PAGE_BYTES:
            raise ExtractPermanentError(
                f"Page at offset {offset} is {len(page.body)} bytes, above the "
                f"{MAX_PAGE_BYTES} byte limit"
            )
        if offset + len(page.rows) > total:
            raise ExtractTransientError(
                f"Dataset returned more rows than the expected {total} (it changed mid-run)"
            )
        key = f"{prefix}payload-{len(files):05d}.json"
        store.put_once(key, page.body, "application/json")
        files.append(
            FileEntry(
                key=key,
                offset=offset,
                row_count=len(page.rows),
                size_bytes=len(page.body),
                sha256=sha256_hex(page.body),
                content_type="application/json",
            )
        )
        offset += len(page.rows)
        if len(page.rows) < page_size:
            break

    if parse_rows_updated_at(soda.get_metadata(DATASET_ID)) != rows_updated_at:
        raise ExtractTransientError(
            "Dataset was replaced during extraction (rowsUpdatedAt changed)"
        )
    if offset != total:
        raise ExtractTransientError(f"Truncated extraction: read {offset} rows, expected {total}")

    manifest = Manifest(
        source_system=SOURCE_SYSTEM,
        dataset_id=DATASET_ID,
        source_url=SOURCE_URL,
        license=LICENSE,
        attribution=ATTRIBUTION,
        batch_id=batch_id,
        extraction_date=extraction_date,
        started_at=started_at,
        finished_at=max(now(), started_at),
        extractor=Extractor(EXTRACTOR_NAME, extractor_version),
        source_rows_updated_at=rows_updated_at,
        app_token_used=soda.uses_app_token,
        query=Query(order=ORDER, page_size=page_size, where=None),
        watermark=Watermark(WATERMARK_COLUMN, "full", None, updated_date),
        schema=EXPECTED_SCHEMA,
        row_count=offset,
        files=tuple(files),
    )
    key = manifest_key(prefix)
    store.put_once(key, manifest.to_json(), "application/json")
    return DivipolaExtractResult("committed", manifest, key)

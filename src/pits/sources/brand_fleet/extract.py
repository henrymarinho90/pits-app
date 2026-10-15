"""Regional brand fleet extractor: SODA -> raw batch in the write-once raw store (D136).

Same protocol as the DIVIPOLA extractor (full snapshot, watermark on rowsUpdatedAt): validate the
metadata schema, count the rows up front (truncation guard; the count query has neither $select
nor $where, D105), page ordered by :id with a $select derived from the contract, validate each
page before storing its bytes untouched, re-check rowsUpdatedAt and the total, and only then
write manifest.json (the commit marker). Manifest.schema records the requested columns, so a
Risaralda batch never lists `placa`. A batch whose latest committed rowsUpdatedAt is the same
is `unchanged` unless forced.
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
from pits.sources.brand_fleet.contract import (
    LICENSE,
    MAX_PAGE_BYTES,
    ORDER,
    PAGE_SIZE,
    WATERMARK_COLUMN,
    BrandFleetSource,
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

EXTRACTOR_NAME = "pits.sources.brand_fleet"
_INT_RE = re.compile(r"[0-9]+")

Outcome = Literal["committed", "unchanged"]


@dataclass(frozen=True)
class BrandFleetExtractResult:
    outcome: Outcome
    manifest: Manifest  # for "unchanged": the latest committed batch (nothing was written)
    manifest_key: str

    @property
    def rows_updated(self) -> str:
        """UTC date of the source rowsUpdatedAt of the batch (the watermark)."""
        to_observed = self.manifest.watermark.to_observed
        return "none" if to_observed is None else to_observed.isoformat()


def extract_brand_fleet(
    soda: SodaClient,
    store: RawStore,
    source: BrandFleetSource,
    *,
    force: bool,
    now: Callable[[], datetime],
    new_batch_id: Callable[[], str],
    extractor_version: str,
    page_size: int = PAGE_SIZE,
) -> BrandFleetExtractResult:
    """Extract one regional dataset into one committed raw batch; see module docstring."""
    try:
        return _extract(soda, store, source, force, now, new_batch_id, extractor_version, page_size)
    except (SodaTransientError, RawStoreTransientError) as exc:
        raise ExtractTransientError(str(exc)) from exc
    except (SodaPermanentError, RawStoreError, ManifestError) as exc:
        raise ExtractPermanentError(str(exc)) from exc


def _read_total(soda: SodaClient, source: BrandFleetSource) -> int:
    page = soda.get_page(source.dataset_id, {"$select": "count(*)"})
    if len(page.rows) != 1 or set(page.rows[0]) != {"count"}:
        raise ExtractPermanentError("Count query returned an unexpected shape")
    count = page.rows[0]["count"]
    if not isinstance(count, str) or not _INT_RE.fullmatch(count) or int(count) < 1:
        raise ExtractPermanentError("Row count is not a positive integer string")
    return int(count)


def _validate_page(source: BrandFleetSource, page: RawPage, offset: int) -> None:
    for i, row in enumerate(page.rows):
        try:
            validate_row(source, row)
        except RowError as exc:
            raise ExtractPermanentError(exc.at(f"row {offset + i}")) from None


def _extract(
    soda: SodaClient,
    store: RawStore,
    source: BrandFleetSource,
    force: bool,
    now: Callable[[], datetime],
    new_batch_id: Callable[[], str],
    extractor_version: str,
    page_size: int,
) -> BrandFleetExtractResult:
    started_at = now()
    if started_at.tzinfo is None:
        raise ValueError("now() must return a timezone-aware datetime")
    extraction_date = started_at.astimezone(UTC).date()

    rows_updated_at = check_metadata(soda, source.dataset_id, source.source_schema)
    total = _read_total(soda, source)

    if not force:
        previous = find_latest_committed(store, source.source_system, source.dataset_id)
        if previous is not None and previous.source_rows_updated_at == rows_updated_at:
            key = manifest_key(
                batch_prefix(source.source_system, previous.extraction_date, previous.batch_id)
            )
            return BrandFleetExtractResult("unchanged", previous, key)

    try:
        updated_date = datetime.fromtimestamp(rows_updated_at, UTC).date()
    except (OverflowError, OSError, ValueError):
        raise ExtractPermanentError("Metadata rowsUpdatedAt is not a valid timestamp") from None

    batch_id = new_batch_id()  # only when a batch will actually be written
    prefix = batch_prefix(source.source_system, extraction_date, batch_id)
    files: list[FileEntry] = []
    offset = 0
    while True:
        page = soda.get_page(
            source.dataset_id,
            {"$select": source.select, "$order": ORDER, "$limit": page_size, "$offset": offset},
        )
        if not page.rows:
            break  # an empty page is never written
        _validate_page(source, page, offset)
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

    if parse_rows_updated_at(soda.get_metadata(source.dataset_id)) != rows_updated_at:
        raise ExtractTransientError(
            "Dataset was replaced during extraction (rowsUpdatedAt changed)"
        )
    if offset != total:
        raise ExtractTransientError(f"Truncated extraction: read {offset} rows, expected {total}")

    manifest = Manifest(
        source_system=source.source_system,
        dataset_id=source.dataset_id,
        source_url=source.source_url,
        license=LICENSE,
        attribution=source.attribution,
        batch_id=batch_id,
        extraction_date=extraction_date,
        started_at=started_at,
        finished_at=max(now(), started_at),
        extractor=Extractor(EXTRACTOR_NAME, extractor_version),
        source_rows_updated_at=rows_updated_at,
        app_token_used=soda.uses_app_token,
        query=Query(order=ORDER, page_size=page_size, where=None),
        watermark=Watermark(WATERMARK_COLUMN, "full", None, updated_date),
        schema=source.requested_schema,
        row_count=offset,
        files=tuple(files),
    )
    key = manifest_key(prefix)
    store.put_once(key, manifest.to_json(), "application/json")
    return BrandFleetExtractResult("committed", manifest, key)

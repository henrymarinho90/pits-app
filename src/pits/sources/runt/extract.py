"""RUNT fleet snapshot extractor: SODA -> raw batch in the write-once raw store (D96).

The dataset is a full snapshot of one publication (year+month). Every run reads it whole:
validate the metadata schema, confirm there is exactly one publication (and its row count),
page ordered by :id, validate each page and store its bytes untouched, re-check rowsUpdatedAt
and the row total, and only then write manifest.json (the commit marker). If the latest
committed batch has the same rowsUpdatedAt nothing is written (outcome=unchanged) unless forced.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

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
from pits.sources.extract_common import (
    ExtractPermanentError,
    ExtractTransientError,
    check_metadata,
    parse_rows_updated_at,
)
from pits.sources.runt.contract import (
    ATTRIBUTION,
    DATASET_ID,
    EXPECTED_SCHEMA,
    LICENSE,
    MAX_PAGE_BYTES,
    MONTH_COLUMN,
    MONTHS,
    ORDER,
    PAGE_SIZE,
    SOURCE_SYSTEM,
    SOURCE_URL,
    WATERMARK_COLUMN,
    YEAR_COLUMN,
    RowError,
    validate_row,
)
from pits.sources.soda.client import (
    RawPage,
    SodaClient,
    SodaPermanentError,
    SodaTransientError,
)

EXTRACTOR_NAME = "pits.sources.runt"
_INT_RE = re.compile(r"[0-9]+")
_YEAR_RE = re.compile(r"[0-9]{4}")

Outcome = Literal["committed", "unchanged"]


@dataclass(frozen=True)
class Publication:
    year: int
    month: int

    def first_day(self) -> date:
        return date(self.year, self.month, 1)

    def label(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


@dataclass(frozen=True)
class RuntExtractResult:
    outcome: Outcome
    manifest: Manifest  # for "unchanged": the latest committed batch (nothing was written)
    manifest_key: str

    @property
    def publication(self) -> str:
        to_observed = self.manifest.watermark.to_observed
        return "none" if to_observed is None else f"{to_observed.year:04d}-{to_observed.month:02d}"


def extract_runt(
    soda: SodaClient,
    store: RawStore,
    *,
    force: bool,
    now: Callable[[], datetime],
    new_batch_id: Callable[[], str],
    extractor_version: str,
    page_size: int = PAGE_SIZE,
) -> RuntExtractResult:
    """Extract the RUNT snapshot into one committed raw batch; see module docstring."""
    try:
        return _extract(soda, store, force, now, new_batch_id, extractor_version, page_size)
    except (SodaTransientError, RawStoreTransientError) as exc:
        raise ExtractTransientError(str(exc)) from exc
    except (SodaPermanentError, RawStoreError, ManifestError) as exc:
        raise ExtractPermanentError(str(exc)) from exc


def _extract(
    soda: SodaClient,
    store: RawStore,
    force: bool,
    now: Callable[[], datetime],
    new_batch_id: Callable[[], str],
    extractor_version: str,
    page_size: int,
) -> RuntExtractResult:
    started_at = now()
    if started_at.tzinfo is None:
        raise ValueError("now() must return a timezone-aware datetime")
    extraction_date = started_at.astimezone(UTC).date()

    rows_updated_at = check_metadata(soda, DATASET_ID, EXPECTED_SCHEMA)
    publication, total = _read_publication(soda)

    if not force:
        previous = find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID)
        if previous is not None and previous.source_rows_updated_at == rows_updated_at:
            key = manifest_key(
                batch_prefix(SOURCE_SYSTEM, previous.extraction_date, previous.batch_id)
            )
            return RuntExtractResult("unchanged", previous, key)

    batch_id = new_batch_id()  # only when a batch will actually be written
    prefix = batch_prefix(SOURCE_SYSTEM, extraction_date, batch_id)
    files: list[FileEntry] = []
    offset = 0
    while True:
        page = soda.get_page(DATASET_ID, {"$order": ORDER, "$limit": page_size, "$offset": offset})
        if not page.rows:
            break  # an empty page is never written
        _validate_page(page, offset, publication)
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
        watermark=Watermark(WATERMARK_COLUMN, "full", None, publication.first_day()),
        schema=EXPECTED_SCHEMA,
        row_count=offset,
        files=tuple(files),
    )
    key = manifest_key(prefix)
    store.put_once(key, manifest.to_json(), "application/json")
    return RuntExtractResult("committed", manifest, key)


def _parse_publication(year: Any, month: Any, where: str) -> Publication:
    if not isinstance(year, str) or not _YEAR_RE.fullmatch(year):
        raise ExtractPermanentError(f"{where}.{YEAR_COLUMN} is not a 4-digit year string")
    if not isinstance(month, str) or month not in MONTHS:
        raise ExtractPermanentError(
            f"{where}.{MONTH_COLUMN} is not a known month (ENERO..DICIEMBRE)"
        )
    return Publication(int(year), MONTHS[month])


def _read_publication(soda: SodaClient) -> tuple[Publication, int]:
    """Return the single publication of the dataset and its expected row count."""
    page = soda.get_page(
        DATASET_ID,
        {
            "$select": f"{YEAR_COLUMN},{MONTH_COLUMN},count(*)",
            "$group": f"{YEAR_COLUMN},{MONTH_COLUMN}",
        },
    )
    if len(page.rows) != 1:
        raise ExtractPermanentError(
            f"Expected exactly 1 publication in the dataset, found {len(page.rows)}"
        )
    group = page.rows[0]
    if set(group) != {YEAR_COLUMN, MONTH_COLUMN, "count"}:
        raise ExtractPermanentError("Publication query returned unexpected keys")
    publication = _parse_publication(group[YEAR_COLUMN], group[MONTH_COLUMN], "publication")
    count = group["count"]
    if not isinstance(count, str) or not _INT_RE.fullmatch(count) or int(count) < 1:
        raise ExtractPermanentError("Publication count is not a positive integer string")
    return publication, int(count)


def _validate_page(page: RawPage, offset: int, publication: Publication) -> None:
    for i, row in enumerate(page.rows):
        try:
            validate_row(row, (publication.year, publication.month))
        except RowError as exc:
            raise ExtractPermanentError(exc.at(f"row {offset + i}")) from None

"""TRM extractor: SODA -> raw batch (payload pages + manifest) in the write-once raw store.

Flow (D64-D66): validate metadata schema BEFORE writing anything, page through the dataset
ordered by (vigenciadesde, :id), validate each page and store its bytes untouched, re-check that
the dataset was not replaced mid-run, and only then write manifest.json (the commit marker).
Only one page is held in memory at a time.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
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
from pits.sources.soda.client import (
    RawPage,
    SodaClient,
    SodaPermanentError,
    SodaTransientError,
)
from pits.sources.trm.contract import (
    ATTRIBUTION,
    BACKFILL_FROM,
    DATASET_ID,
    DATE_RE,
    EXPECTED_COLUMNS,
    EXPECTED_SCHEMA,
    LICENSE,
    ORDER,
    PAGE_SIZE,
    SOURCE_SYSTEM,
    SOURCE_URL,
    WATERMARK_COLUMN,
)

Mode = Literal["incremental", "full", "since"]
EXTRACTOR_NAME = "pits.sources.trm"


class ExtractError(RuntimeError):
    """Base class for extractor failures; messages never contain secrets."""


class ExtractPermanentError(ExtractError):
    """Retrying will not help (schema drift, invalid rows, write conflict, bad manifest)."""


class ExtractTransientError(ExtractError):
    """Retrying later may succeed (network, 5xx, dataset replaced mid-run, empty dataset)."""


class ExtractUsageError(ExtractError):
    """The requested extraction is inconsistent (e.g. --since would leave a gap)."""


@dataclass(frozen=True)
class ExtractResult:
    manifest: Manifest
    manifest_key: str


def extract_trm(
    soda: SodaClient,
    store: RawStore,
    *,
    mode: Mode,
    since: date | None,
    now: Callable[[], datetime],
    new_batch_id: Callable[[], str],
    extractor_version: str,
    page_size: int = PAGE_SIZE,
) -> ExtractResult:
    """Extract the TRM dataset into one committed raw batch; see module docstring."""
    if (mode == "since") != (since is not None):
        raise ExtractUsageError("since is required if and only if mode is 'since'")
    try:
        return _extract(soda, store, mode, since, now, new_batch_id, extractor_version, page_size)
    except (SodaTransientError, RawStoreTransientError) as exc:
        raise ExtractTransientError(str(exc)) from exc
    except (SodaPermanentError, RawStoreError, ManifestError) as exc:
        # RawObjectExistsError is a RawStoreError: a write-once conflict is permanent.
        raise ExtractPermanentError(str(exc)) from exc


def _extract(
    soda: SodaClient,
    store: RawStore,
    mode: Mode,
    since: date | None,
    now: Callable[[], datetime],
    new_batch_id: Callable[[], str],
    extractor_version: str,
    page_size: int,
) -> ExtractResult:
    started_at = now()
    if started_at.tzinfo is None:
        raise ValueError("now() must return a timezone-aware datetime")
    extraction_date = started_at.astimezone(UTC).date()
    batch_id = new_batch_id()
    prefix = batch_prefix(SOURCE_SYSTEM, extraction_date, batch_id)

    rows_updated_at = _check_metadata(soda)

    previous = None
    if mode in ("incremental", "since"):
        previous = find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID)
    previous_watermark = previous.watermark.to_observed if previous else None

    manifest_mode: Mode = mode
    from_exclusive: date | None = None
    where: str | None = None
    if mode == "incremental":
        if previous_watermark is None:
            manifest_mode = "full"  # no committed batch yet: backfill, recorded as full
        else:
            from_exclusive = previous_watermark
            where = f"{WATERMARK_COLUMN} > '{from_exclusive.isoformat()}T00:00:00.000'"
    elif since is not None:
        from_exclusive = since - timedelta(days=1)
        # Without a previous batch the reference is the start of the dataset.
        effective = previous_watermark or (BACKFILL_FROM - timedelta(days=1))
        if from_exclusive > effective:
            raise ExtractUsageError(
                f"since {since} is more than one day after the watermark {effective}: "
                "it would leave a gap"
            )
        where = f"{WATERMARK_COLUMN} >= '{since.isoformat()}T00:00:00.000'"

    files: list[FileEntry] = []
    last_date: date | None = None
    offset = 0
    while True:
        params: dict[str, str | int] = {"$order": ORDER, "$limit": page_size, "$offset": offset}
        if where is not None:
            params["$where"] = where
        page = soda.get_page(DATASET_ID, params)
        if not page.rows:
            break  # an empty page is never written
        last_date = _validate_page(page, offset, last_date, from_exclusive)
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

    if _rows_updated_at(soda) != rows_updated_at:
        raise ExtractTransientError(
            "Dataset was replaced during extraction (rowsUpdatedAt changed)"
        )

    if last_date is not None:
        to_observed: date | None = last_date
    elif manifest_mode == "full":
        raise ExtractTransientError("Dataset returned no rows on a full extraction")
    elif manifest_mode == "incremental":
        to_observed = from_exclusive  # empty batch carries the watermark forward
    else:  # since, empty
        to_observed = previous_watermark

    manifest = Manifest(
        source_system=SOURCE_SYSTEM,
        dataset_id=DATASET_ID,
        source_url=SOURCE_URL,
        license=LICENSE,
        attribution=ATTRIBUTION,
        batch_id=batch_id,
        extraction_date=extraction_date,
        started_at=started_at,
        # max(): a clock step backwards must not produce finished_at < started_at.
        finished_at=max(now(), started_at),
        extractor=Extractor(EXTRACTOR_NAME, extractor_version),
        source_rows_updated_at=rows_updated_at,
        app_token_used=soda.uses_app_token,
        query=Query(order=ORDER, page_size=page_size, where=where),
        watermark=Watermark(WATERMARK_COLUMN, manifest_mode, from_exclusive, to_observed),
        schema=EXPECTED_SCHEMA,
        row_count=offset,
        files=tuple(files),
    )
    key = manifest_key(prefix)
    store.put_once(key, manifest.to_json(), "application/json")
    return ExtractResult(manifest=manifest, manifest_key=key)


def _parse_rows_updated_at(meta: dict[str, Any]) -> int:
    value = meta.get("rowsUpdatedAt")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExtractPermanentError("Metadata rowsUpdatedAt is missing or not an integer")
    return value


def _rows_updated_at(soda: SodaClient) -> int:
    return _parse_rows_updated_at(soda.get_metadata(DATASET_ID))


def _check_metadata(soda: SodaClient) -> int:
    """Validate the non-system column schema exactly; return rowsUpdatedAt."""
    meta = soda.get_metadata(DATASET_ID)
    columns = meta.get("columns")
    if not isinstance(columns, list) or not all(isinstance(c, dict) for c in columns):
        raise ExtractPermanentError("Metadata has no valid 'columns' list")
    actual = {
        c.get("fieldName"): c.get("dataTypeName")
        for c in columns
        if not str(c.get("fieldName", "")).startswith(":")
    }
    expected = {c.name: c.data_type for c in EXPECTED_SCHEMA}
    if actual != expected:
        raise ExtractPermanentError(f"Schema drift in metadata: expected {expected}, got {actual}")
    return _parse_rows_updated_at(meta)


def _parse_date(value: Any, where: str) -> date:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        raise ExtractPermanentError(
            f"{where} is not a midnight timestamp (YYYY-MM-DDT00:00:00.000)"
        )
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ExtractPermanentError(f"{where} is not a valid date") from exc


def _validate_page(
    page: RawPage, offset: int, last_date: date | None, from_exclusive: date | None
) -> date:
    """Validate rows of one page; return the last vigenciadesde (strictly ascending overall)."""
    current = last_date
    for i, row in enumerate(page.rows):
        where = f"row {offset + i}"
        if set(row) != EXPECTED_COLUMNS:
            raise ExtractPermanentError(
                f"{where} has wrong keys (missing={sorted(EXPECTED_COLUMNS - set(row))}, "
                f"unexpected={sorted(set(row) - EXPECTED_COLUMNS)})"
            )
        for name in ("valor", "unidad"):
            if not isinstance(row[name], str):
                raise ExtractPermanentError(f"{where}.{name} must be a string")
        try:
            valor = Decimal(row["valor"])
        except InvalidOperation:
            valor = None
        if valor is None or not valor.is_finite():
            raise ExtractPermanentError(f"{where}.valor is not a finite decimal number")
        parsed = _parse_date(row["vigenciadesde"], f"{where}.vigenciadesde")
        _parse_date(row["vigenciahasta"], f"{where}.vigenciahasta")
        if from_exclusive is not None and parsed <= from_exclusive:
            raise ExtractPermanentError(f"{where}.vigenciadesde is not after the watermark")
        if current is not None and parsed <= current:
            raise ExtractPermanentError(f"{where}.vigenciadesde is duplicated or out of order")
        current = parsed
    return current  # pages are never empty, so current is a date here

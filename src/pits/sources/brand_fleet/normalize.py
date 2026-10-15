"""Normalize the committed raw regional brand fleet batches into regional_fleet_brand (D137).

Replay from raw only: it never talks to SODA. Each source is a full snapshot, so the last
committed batch by commit order (D76) of one source_system is the only input; its fingerprint
comes from its raw manifest alone, so an already committed artifact is detected without reading
any payload.

The artifact aggregates the rows by (clase, marca, linea, servicio, estado) with a vehicle_count,
keeping the values as published and dropping every other column (the plate included). It holds
only the aggregated keys in memory, never the rows. Conservation: the sum of vehicle_count must
equal the row_count of the raw manifest, otherwise the run fails.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date

from pits.ingestion.batch_reader import iter_verified_pages
from pits.ingestion.manifest import (
    Manifest,
    ManifestError,
    list_committed,
    manifest_key,
    sha256_hex,
)
from pits.ingestion.raw_store import (
    RawObjectNotFoundError,
    RawStore,
    RawStoreError,
    RawStoreTransientError,
    batch_prefix,
)
from pits.normalized.brand_fleet_csv import (
    CONTENT_TYPE,
    CSV_NAME,
    BrandFleetCsvError,
    Row,
    serialize_brand_count,
)
from pits.normalized.brand_fleet_manifest import (
    BRAND_FLEET_MANIFEST_NAME,
    BrandFleetManifest,
    BrandFleetManifestError,
    artifact_prefix,
)
from pits.normalized.commit import NormalizedOutcome, commit_objects
from pits.normalized.fingerprint import InputRef, Transform, compute_input_fingerprint
from pits.normalized.manifest import Output
from pits.sources.brand_fleet.contract import (
    WATERMARK_COLUMN,
    BrandFleetSource,
    RowError,
    validate_row,
)
from pits.sources.normalize_common import NormalizePermanentError, NormalizeTransientError

TRANSFORM_NAME = "brand_fleet_to_brand_count"
DEFAULT_RULES_VERSION = "brand-fleet-v1"

__all__ = [
    "DEFAULT_RULES_VERSION",
    "TRANSFORM_NAME",
    "BrandFleetResult",
    "NormalizePermanentError",
    "NormalizeTransientError",
    "normalize_brand_fleet",
]

_Key = tuple[str, str, str, str, str]


@dataclass(frozen=True)
class BrandFleetResult:
    outcome: NormalizedOutcome
    rows_updated: date
    fingerprint: str
    batch_id: str
    rows: int  # CSV rows
    vehicles: int  # sum of vehicle_count (= rows of the raw batch)
    manifest_key: str


def normalize_brand_fleet(
    raw_store: RawStore,
    normalized_store: RawStore,
    source: BrandFleetSource,
    *,
    raw_bucket: str,
    rules_version: str = DEFAULT_RULES_VERSION,
) -> BrandFleetResult:
    """Replay the latest committed raw batch of `source` into one write-once CSV + manifest."""
    try:
        return _normalize(raw_store, normalized_store, source, raw_bucket, rules_version)
    except RawStoreTransientError as exc:
        raise NormalizeTransientError(str(exc)) from exc
    except (
        RawStoreError,
        ManifestError,
        BrandFleetCsvError,
        BrandFleetManifestError,
    ) as exc:
        raise NormalizePermanentError(str(exc)) from exc


def _check_batch(source: BrandFleetSource, m: Manifest) -> date:
    """Return the rows_updated date of a raw batch; the extractor guarantees a full snapshot."""
    where = f"batch {m.batch_id}"
    if m.watermark.mode != "full" or m.watermark.column != WATERMARK_COLUMN:
        raise NormalizePermanentError(f"{where} is not a full snapshot of {source.source_system}")
    if m.schema != source.requested_schema:
        raise NormalizePermanentError(
            f"{where} has a schema other than the requested columns of {source.source_system}"
        )
    if m.watermark.to_observed is None or m.row_count < 1:
        raise NormalizePermanentError(f"{where} has no rows or no rowsUpdatedAt date")
    return m.watermark.to_observed


def _input_ref(raw_store: RawStore, m: Manifest) -> InputRef:
    key = manifest_key(batch_prefix(m.source_system, m.extraction_date, m.batch_id))
    data = raw_store.get(key)
    if Manifest.from_json(data) != m:
        raise ManifestError(f"{key}: manifest changed while reading")
    return InputRef(
        batch_id=m.batch_id,
        extraction_date=m.extraction_date,
        finished_at=m.finished_at,
        mode=m.watermark.mode,
        manifest_key=key,
        manifest_sha256=sha256_hex(data),
    )


def _existing(store: RawStore, key: str, fingerprint: str) -> BrandFleetManifest | None:
    """The committed manifest at `key` if there is one (strictly validated), else None."""
    try:
        data = store.get(key)
    except RawObjectNotFoundError:
        return None
    manifest = BrandFleetManifest.from_json(data)
    if manifest.input_fingerprint != fingerprint or manifest.manifest_key != key:
        raise BrandFleetManifestError(f"{key}: content does not match its key")
    return manifest


def _aggregate(raw_store: RawStore, source: BrandFleetSource, m: Manifest) -> list[Row]:
    counts: dict[_Key, int] = {}
    for page in iter_verified_pages(raw_store, m):
        for i, row in enumerate(page.rows):
            try:
                validate_row(source, row)
            except RowError as exc:
                raise NormalizePermanentError(exc.at(f"{page.entry.key}#row={i}")) from None
            key: _Key = (
                sys.intern(row["clase"]),
                sys.intern(row["marca"]),
                sys.intern(row["linea"]),
                sys.intern(row.get("servicio", "")),
                sys.intern(row.get("estado", "")),
            )
            counts[key] = counts.get(key, 0) + 1
    return [(*key, counts[key]) for key in sorted(counts)]


def _normalize(
    raw_store: RawStore,
    normalized_store: RawStore,
    source: BrandFleetSource,
    raw_bucket: str,
    rules_version: str,
) -> BrandFleetResult:
    committed = list_committed(raw_store, source.source_system, source.dataset_id)  # D76 order
    if not committed:
        raise NormalizePermanentError(f"No committed raw batch found for {source.source_system}")
    m = committed[-1]
    rows_updated = _check_batch(source, m)
    ref = _input_ref(raw_store, m)
    transform = Transform(TRANSFORM_NAME, rules_version)
    fingerprint = compute_input_fingerprint(transform, raw_bucket, (ref,))
    prefix = artifact_prefix(source.source_system, rows_updated, fingerprint)
    out_key = prefix + BRAND_FLEET_MANIFEST_NAME

    existing = _existing(normalized_store, out_key, fingerprint)
    if existing is not None:  # committed: payloads are not read
        return BrandFleetResult(
            NormalizedOutcome.ALREADY_PRESENT,
            rows_updated,
            fingerprint,
            m.batch_id,
            existing.row_count,
            existing.vehicle_total,
            out_key,
        )

    rows = _aggregate(raw_store, source, m)
    vehicles = sum(r[5] for r in rows)
    if vehicles != m.row_count:
        raise NormalizePermanentError(
            f"Conservation failed for batch {m.batch_id}: aggregated {vehicles} vehicles, "
            f"raw manifest has {m.row_count} rows"
        )
    body = serialize_brand_count(rows, ref.manifest_key)
    csv_key = prefix + CSV_NAME
    manifest = BrandFleetManifest(
        source_system=source.source_system,
        dataset_id=source.dataset_id,
        transform=transform,
        raw_bucket=raw_bucket,
        inputs=(ref,),
        input_fingerprint=fingerprint,
        rows_updated=rows_updated,
        row_count=len(rows),
        vehicle_total=vehicles,
        output=Output(csv_key, sha256_hex(body), len(body), CONTENT_TYPE),
    )
    outcome = commit_objects(
        normalized_store, [(csv_key, body, CONTENT_TYPE)], out_key, manifest.to_json()
    )
    return BrandFleetResult(
        outcome, rows_updated, fingerprint, m.batch_id, len(rows), vehicles, out_key
    )

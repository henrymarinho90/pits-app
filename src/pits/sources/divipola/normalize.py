"""Normalize the committed raw DIVIPOLA batches into the divipola_municipality artifact (D123).

Replay from raw only: it never talks to SODA. The dataset is a full snapshot, so the last
committed batch by commit order (D76) is the only input; its fingerprint comes from its raw
manifest alone, so an already committed artifact is detected without reading any payload.
"""

from __future__ import annotations

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
from pits.normalized.commit import NormalizedOutcome, commit_objects
from pits.normalized.divipola_csv import (
    CONTENT_TYPE,
    CSV_NAME,
    DivipolaCsvError,
    serialize_divipola,
)
from pits.normalized.divipola_manifest import (
    DIVIPOLA_MANIFEST_NAME,
    DivipolaManifest,
    DivipolaManifestError,
    artifact_prefix,
)
from pits.normalized.fingerprint import InputRef, Transform, compute_input_fingerprint
from pits.normalized.manifest import Output
from pits.sources.divipola.contract import (
    DATASET_ID,
    EXPECTED_SCHEMA,
    SOURCE_SYSTEM,
    WATERMARK_COLUMN,
)
from pits.sources.divipola.parse import (
    DivipolaDataError,
    Record,
    parse_page,
    sort_and_check_unique,
)
from pits.sources.normalize_common import NormalizePermanentError, NormalizeTransientError

TRANSFORM_NAME = "divipola_to_municipality"
DEFAULT_RULES_VERSION = "divipola-v1"

__all__ = [
    "DEFAULT_RULES_VERSION",
    "TRANSFORM_NAME",
    "DivipolaResult",
    "NormalizePermanentError",
    "NormalizeTransientError",
    "normalize_divipola",
]


@dataclass(frozen=True)
class DivipolaResult:
    outcome: NormalizedOutcome
    rows_updated: date
    fingerprint: str
    batch_id: str
    rows: int
    manifest_key: str


def normalize_divipola(
    raw_store: RawStore,
    normalized_store: RawStore,
    *,
    raw_bucket: str,
    rules_version: str = DEFAULT_RULES_VERSION,
) -> DivipolaResult:
    """Replay the latest committed raw batch into one write-once CSV + manifest."""
    try:
        return _normalize(raw_store, normalized_store, raw_bucket, rules_version)
    except RawStoreTransientError as exc:
        raise NormalizeTransientError(str(exc)) from exc
    except (
        RawStoreError,
        ManifestError,
        DivipolaDataError,
        DivipolaCsvError,
        DivipolaManifestError,
    ) as exc:
        raise NormalizePermanentError(str(exc)) from exc


def _check_batch(m: Manifest) -> date:
    """Return the rows_updated date of a raw batch; the extractor guarantees a full snapshot."""
    where = f"batch {m.batch_id}"
    if m.watermark.mode != "full" or m.watermark.column != WATERMARK_COLUMN:
        raise NormalizePermanentError(f"{where} is not a DIVIPOLA full snapshot")
    if m.schema != EXPECTED_SCHEMA:
        raise NormalizePermanentError(f"{where} has a schema other than the DIVIPOLA contract")
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


def _existing(store: RawStore, key: str, fingerprint: str) -> DivipolaManifest | None:
    """The committed manifest at `key` if there is one (strictly validated), else None."""
    try:
        data = store.get(key)
    except RawObjectNotFoundError:
        return None
    manifest = DivipolaManifest.from_json(data)
    if manifest.input_fingerprint != fingerprint or manifest.manifest_key != key:
        raise DivipolaManifestError(f"{key}: content does not match its key")
    return manifest


def _normalize(
    raw_store: RawStore, normalized_store: RawStore, raw_bucket: str, rules_version: str
) -> DivipolaResult:
    committed = list_committed(raw_store, SOURCE_SYSTEM, DATASET_ID)  # in commit order (D76)
    if not committed:
        raise NormalizePermanentError("No committed raw DIVIPOLA batch found")
    m = committed[-1]
    rows_updated = _check_batch(m)
    ref = _input_ref(raw_store, m)
    transform = Transform(TRANSFORM_NAME, rules_version)
    fingerprint = compute_input_fingerprint(transform, raw_bucket, (ref,))
    prefix = artifact_prefix(rows_updated, fingerprint)
    out_key = prefix + DIVIPOLA_MANIFEST_NAME

    existing = _existing(normalized_store, out_key, fingerprint)
    if existing is not None:  # committed: payloads are not read
        return DivipolaResult(
            NormalizedOutcome.ALREADY_PRESENT,
            rows_updated,
            fingerprint,
            m.batch_id,
            existing.row_count,
            out_key,
        )

    records: list[Record] = []
    payload_keys: list[str] = []
    for page in iter_verified_pages(raw_store, m):
        records.extend(parse_page(page.rows, page_key=page.entry.key, page_index=len(payload_keys)))
        payload_keys.append(page.entry.key)
    sort_and_check_unique(records, payload_keys)
    body = serialize_divipola(records, payload_keys)
    csv_key = prefix + CSV_NAME
    manifest = DivipolaManifest(
        source_system=SOURCE_SYSTEM,
        dataset_id=DATASET_ID,
        transform=transform,
        raw_bucket=raw_bucket,
        inputs=(ref,),
        input_fingerprint=fingerprint,
        rows_updated=rows_updated,
        row_count=len(records),
        output=Output(csv_key, sha256_hex(body), len(body), CONTENT_TYPE),
    )
    outcome = commit_objects(
        normalized_store, [(csv_key, body, CONTENT_TYPE)], out_key, manifest.to_json()
    )
    return DivipolaResult(outcome, rows_updated, fingerprint, m.batch_id, len(records), out_key)

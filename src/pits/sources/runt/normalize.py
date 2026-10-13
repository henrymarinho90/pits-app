"""Normalize committed raw RUNT batches into vehicle_fleet_snapshot artifacts (D97, D98).

Replay from raw only: it never talks to SODA. One artifact per publication (year+month) present
in raw; in each publication the last committed batch by commit order (D76) wins, and a new
publication never touches another one. The fingerprint is computed from the winning batch's raw
manifest alone, so an already committed artifact is detected without reading any payload.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

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
from pits.normalized.fingerprint import InputRef, Transform, compute_input_fingerprint
from pits.normalized.fleet_csv import CONTENT_TYPE, FleetCsvError, logical_content, serialize_fleet
from pits.normalized.fleet_manifest import (
    FLEET_MANIFEST_NAME,
    FleetManifest,
    FleetManifestError,
    PartEntry,
    Publication,
    artifact_prefix,
)
from pits.sources.normalize_common import NormalizePermanentError, NormalizeTransientError
from pits.sources.runt.contract import (
    DATASET_ID,
    EXPECTED_SCHEMA,
    SOURCE_SYSTEM,
    WATERMARK_COLUMN,
)
from pits.sources.runt.parse import (
    COUNT_INDEX,
    Record,
    RuntDataError,
    parse_page,
    sort_and_check_unique,
)

TRANSFORM_NAME = "runt_to_vehicle_fleet_snapshot"
DEFAULT_RULES_VERSION = "runt-v1"

__all__ = [
    "DEFAULT_RULES_VERSION",
    "TRANSFORM_NAME",
    "FleetResult",
    "NormalizePermanentError",
    "NormalizeTransientError",
    "normalize_runt",
]


@dataclass(frozen=True)
class FleetResult:
    outcome: NormalizedOutcome
    publication: str
    fingerprint: str
    inputs: int
    batch_id: str
    rows: int
    parts: int
    manifest_key: str


def normalize_runt(
    raw_store: RawStore,
    normalized_store: RawStore,
    *,
    raw_bucket: str,
    rules_version: str = DEFAULT_RULES_VERSION,
) -> Iterator[FleetResult]:
    """Yield one result per publication (ascending), as soon as each artifact is committed."""
    try:
        yield from _normalize(raw_store, normalized_store, raw_bucket, rules_version)
    except RawStoreTransientError as exc:
        raise NormalizeTransientError(str(exc)) from exc
    except (
        RawStoreError,
        ManifestError,
        RuntDataError,
        FleetCsvError,
        FleetManifestError,
    ) as exc:
        raise NormalizePermanentError(str(exc)) from exc


def _publication_of(m: Manifest) -> Publication:
    """Publication of a raw batch; the extractor guarantees a full snapshot of exactly one."""
    where = f"batch {m.batch_id}"
    if m.watermark.mode != "full" or m.watermark.column != WATERMARK_COLUMN:
        raise NormalizePermanentError(f"{where} is not a RUNT full snapshot")
    if m.schema != EXPECTED_SCHEMA:
        raise NormalizePermanentError(f"{where} has a schema other than the RUNT contract")
    if m.watermark.to_observed is None or m.row_count < 1:
        raise NormalizePermanentError(f"{where} has no rows or no publication")
    first_day = m.watermark.to_observed
    return Publication(first_day.year, first_day.month)


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


def _winners(raw_store: RawStore) -> list[tuple[Publication, Manifest]]:
    committed = list_committed(raw_store, SOURCE_SYSTEM, DATASET_ID)  # in commit order (D76)
    if not committed:
        raise NormalizePermanentError("No committed raw RUNT batch found")
    winner: dict[Publication, Manifest] = {}
    for m in committed:
        winner[_publication_of(m)] = m  # later in commit order replaces earlier
    return sorted(winner.items(), key=lambda item: (item[0].year, item[0].month))


def _existing(
    store: RawStore, key: str, fingerprint: str, publication: Publication
) -> FleetManifest | None:
    """The committed manifest at `key` if there is one (strictly validated), else None."""
    try:
        data = store.get(key)
    except RawObjectNotFoundError:
        return None
    manifest = FleetManifest.from_json(data)
    if manifest.input_fingerprint != fingerprint or manifest.publication != publication:
        raise FleetManifestError(f"{key}: content does not match its key")
    return manifest


def _normalize(
    raw_store: RawStore, normalized_store: RawStore, raw_bucket: str, rules_version: str
) -> Iterator[FleetResult]:
    transform = Transform(TRANSFORM_NAME, rules_version)
    for publication, m in _winners(raw_store):
        ref = _input_ref(raw_store, m)
        fingerprint = compute_input_fingerprint(transform, raw_bucket, (ref,))
        prefix = artifact_prefix(publication.label, fingerprint)
        out_key = prefix + FLEET_MANIFEST_NAME

        existing = _existing(normalized_store, out_key, fingerprint, publication)
        if existing is not None:  # committed: payloads are not read
            yield FleetResult(
                NormalizedOutcome.ALREADY_PRESENT,
                publication.label,
                fingerprint,
                1,
                m.batch_id,
                existing.row_count,
                len(existing.parts),
                out_key,
            )
            continue

        records: list[Record] = []
        payload_keys: list[str] = []
        for page in iter_verified_pages(raw_store, m):
            records.extend(
                parse_page(
                    page.rows,
                    page_key=page.entry.key,
                    page_index=len(payload_keys),
                    publication=(publication.year, publication.month),
                )
            )
            payload_keys.append(page.entry.key)
        sort_and_check_unique(records, payload_keys)
        parts = serialize_fleet(records, payload_keys)
        content_sha256, content_size = logical_content(parts)
        entries = tuple(
            PartEntry(f"{prefix}part-{n:05d}.csv", p.sha256, len(p.body), p.row_count)
            for n, p in enumerate(parts)
        )
        manifest = FleetManifest(
            source_system=SOURCE_SYSTEM,
            dataset_id=DATASET_ID,
            transform=transform,
            raw_bucket=raw_bucket,
            inputs=(ref,),
            input_fingerprint=fingerprint,
            publication=publication,
            row_count=len(records),
            vehicle_count_total=sum(r[COUNT_INDEX] for r in records),
            content_sha256=content_sha256,
            content_size_bytes=content_size,
            parts=entries,
        )
        outcome = commit_objects(
            normalized_store,
            [(e.key, p.body, CONTENT_TYPE) for e, p in zip(entries, parts, strict=True)],
            out_key,
            manifest.to_json(),
        )
        yield FleetResult(
            outcome,
            publication.label,
            fingerprint,
            1,
            m.batch_id,
            len(records),
            len(parts),
            out_key,
        )

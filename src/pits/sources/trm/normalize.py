"""Normalize committed raw TRM batches into the fx_rate CSV artifact (D47, D74-D77).

Replay from raw only: it never talks to SODA (no client is accepted).
"""

from __future__ import annotations

from collections.abc import Callable
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
from pits.ingestion.raw_store import RawStore, RawStoreError, RawStoreTransientError, batch_prefix
from pits.normalized.commit import NormalizedOutcome, commit_normalized
from pits.normalized.fx_rate_csv import CONTENT_TYPE, FxRateCsvError, serialize_fx_rate
from pits.normalized.manifest import (
    Coverage,
    InputRef,
    NormalizedManifest,
    NormalizedManifestError,
    Output,
    Transform,
    compute_input_fingerprint,
)
from pits.sources.trm.contract import BACKFILL_FROM, DATASET_ID, SOURCE_SYSTEM
from pits.sources.trm.parse import TrmDataError, TrmRecord, parse_page
from pits.sources.trm.replay import (
    check_coverage,
    expand_daily,
    max_range_days,
    reconstruct,
    select_inputs,
)

TRANSFORM_NAME = "trm_to_fx_rate"
DEFAULT_RULES_VERSION = "trm-v1"
_DATASET = "fx_rate"


class NormalizeError(RuntimeError):
    """Base class of normalize failures."""


class NormalizePermanentError(NormalizeError):
    """Retrying cannot help (bad data, conflict, too large, missing full batch)."""


class NormalizeTransientError(NormalizeError):
    """Network/store failure: the same command may succeed later."""


@dataclass(frozen=True)
class NormalizeResult:
    outcome: NormalizedOutcome
    fingerprint: str
    inputs: int
    baseline_batch_id: str
    rows: int
    coverage_from: date
    coverage_to: date
    max_range_days: int
    csv_key: str
    manifest_key: str


def normalize_trm(
    raw_store: RawStore,
    normalized_store: RawStore,
    *,
    raw_bucket: str,
    rules_version: str = DEFAULT_RULES_VERSION,
) -> NormalizeResult:
    """Replay committed raw batches into one write-once CSV + manifest; see D76."""
    try:
        return _normalize(raw_store, normalized_store, raw_bucket, rules_version)
    except RawStoreTransientError as exc:
        raise NormalizeTransientError(str(exc)) from exc
    except (
        RawStoreError,
        ManifestError,
        TrmDataError,
        FxRateCsvError,
        NormalizedManifestError,
    ) as exc:
        raise NormalizePermanentError(str(exc)) from exc


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


def _reader(raw_store: RawStore) -> Callable[[Manifest], list[TrmRecord]]:
    def read(manifest: Manifest) -> list[TrmRecord]:
        records: list[TrmRecord] = []
        for page in iter_verified_pages(raw_store, manifest):
            records.extend(parse_page(page.rows, page_key=page.entry.key))
        return records

    return read


def _normalize(
    raw_store: RawStore, normalized_store: RawStore, raw_bucket: str, rules_version: str
) -> NormalizeResult:
    plan = select_inputs(list_committed(raw_store, SOURCE_SYSTEM, DATASET_ID))
    refs = tuple(_input_ref(raw_store, m) for m in plan.inputs)
    transform = Transform(TRANSFORM_NAME, rules_version)
    fingerprint = compute_input_fingerprint(transform, raw_bucket, refs)

    state = reconstruct(plan, _reader(raw_store))
    days = expand_daily(state)
    check_coverage(days, BACKFILL_FROM)
    csv_bytes = serialize_fx_rate(days)

    base = (
        f"{_DATASET}/source_system={SOURCE_SYSTEM}/"
        f"inputs_until={plan.inputs[-1].extraction_date.isoformat()}/fingerprint={fingerprint}/"
    )
    csv_key = base + "fx_rate.csv"
    out_manifest_key = base + "manifest.json"
    longest = max_range_days(state)
    manifest = NormalizedManifest(
        source_system=SOURCE_SYSTEM,
        dataset_id=DATASET_ID,
        transform=transform,
        raw_bucket=raw_bucket,
        inputs=refs,
        baseline_batch_id=plan.baseline.batch_id,
        input_fingerprint=fingerprint,
        coverage=Coverage(days[0].rate_date, days[-1].rate_date),
        row_count=len(days),
        max_range_days=longest,
        output=Output(csv_key, sha256_hex(csv_bytes), len(csv_bytes), CONTENT_TYPE),
    )
    outcome = commit_normalized(
        normalized_store,
        csv_key=csv_key,
        csv_bytes=csv_bytes,
        manifest_key=out_manifest_key,
        manifest_bytes=manifest.to_json(),
    )
    return NormalizeResult(
        outcome=outcome,
        fingerprint=fingerprint,
        inputs=len(refs),
        baseline_batch_id=plan.baseline.batch_id,
        rows=len(days),
        coverage_from=days[0].rate_date,
        coverage_to=days[-1].rate_date,
        max_range_days=longest,
        csv_key=csv_key,
        manifest_key=out_manifest_key,
    )

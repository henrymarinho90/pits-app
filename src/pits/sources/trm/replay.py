"""Replay of committed raw TRM batches into daily rates (D76).

Pure logic (no I/O, no clock): the caller supplies manifests and a page reader.
Baseline = last full batch (commit order) plus every later batch applied in order. Per mode
(key = vigenciadesde): full replaces the state; since S deletes valid_from >= S then inserts
(an empty since deletes the tail); incremental upserts rows after from_exclusive (an empty
incremental is a no-op).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from pits.ingestion.manifest import Manifest, commit_order_key
from pits.sources.trm.contract import BACKFILL_FROM
from pits.sources.trm.parse import TrmDataError, TrmRecord


class ReplayError(TrmDataError):
    """The committed batches cannot be replayed (permanent)."""


class CoverageError(TrmDataError):
    """The reconstructed daily series has a gap, an overlap or a wrong start."""


@dataclass(frozen=True)
class ReplayPlan:
    baseline: Manifest
    inputs: tuple[Manifest, ...]  # baseline first, then later batches in commit order


@dataclass(frozen=True)
class FxDay:
    rate_date: date
    rate: Decimal
    source_reference: str


def select_inputs(manifests: Iterable[Manifest]) -> ReplayPlan:
    """Pick the last full batch by commit order and every batch committed after it."""
    ordered = sorted(manifests, key=commit_order_key)
    full_positions = [i for i, m in enumerate(ordered) if m.watermark.mode == "full"]
    if not full_positions:
        raise ReplayError("No committed full batch: run a full extraction first")
    inputs = tuple(ordered[full_positions[-1] :])
    return ReplayPlan(baseline=inputs[0], inputs=inputs)


def reconstruct(
    plan: ReplayPlan, read_records: Callable[[Manifest], Iterable[TrmRecord]]
) -> dict[date, TrmRecord]:
    """Apply the plan's batches in order and return the state keyed by valid_from."""
    state: dict[date, TrmRecord] = {}
    for manifest in plan.inputs:
        records = _checked_batch(manifest, list(read_records(manifest)))
        wm = manifest.watermark
        if wm.mode == "full":
            state = {r.valid_from: r for r in records}
        elif wm.mode == "since":
            if wm.from_exclusive is None:
                raise ReplayError(f"batch {manifest.batch_id}: since batch without from_exclusive")
            start = wm.from_exclusive + timedelta(days=1)
            for r in records:
                if r.valid_from < start:
                    raise ReplayError(
                        f"{r.source_reference}: valid_from {r.valid_from} is before since {start}"
                    )
            deleted = sorted(k for k in state if k >= start)
            if not records and deleted:
                first = state[deleted[0]]
                raise CoverageError(
                    f"batch {manifest.batch_id}: empty since {start} deletes the tail "
                    f"(first deleted {deleted[0]}, {first.source_reference})"
                )
            state = {k: v for k, v in state.items() if k < start}
            state.update((r.valid_from, r) for r in records)
        elif wm.mode == "incremental":
            if wm.from_exclusive is None:
                raise ReplayError(f"batch {manifest.batch_id}: incremental without from_exclusive")
            for r in records:
                if r.valid_from <= wm.from_exclusive:
                    raise ReplayError(
                        f"{r.source_reference}: valid_from {r.valid_from} is not after "
                        f"the watermark {wm.from_exclusive}"
                    )
            state.update((r.valid_from, r) for r in records)
        else:  # unreachable: Manifest validates the mode
            raise ReplayError(f"batch {manifest.batch_id}: unknown mode {wm.mode!r}")
    return state


def _checked_batch(manifest: Manifest, records: list[TrmRecord]) -> list[TrmRecord]:
    """Whole-batch checks: row count and strict vigenciadesde order across pages."""
    if len(records) != manifest.row_count:
        raise ReplayError(
            f"batch {manifest.batch_id}: read {len(records)} rows, manifest says "
            f"{manifest.row_count}"
        )
    for prev, cur in zip(records, records[1:], strict=False):
        if cur.valid_from <= prev.valid_from:
            raise ReplayError(
                f"{cur.source_reference}: vigenciadesde is duplicated or out of order "
                f"across pages (after {prev.source_reference})"
            )
    return records


def expand_daily(state: Mapping[date, TrmRecord]) -> list[FxDay]:
    """One FxDay per calendar day of each range, inclusive (weekends, holidays, future).

    Sorted by date; an overlap yields two entries for the same date, which check_coverage
    reports. Never reads the clock.
    """
    days: list[FxDay] = []
    for record in sorted(state.values(), key=lambda r: r.valid_from):
        for offset in range((record.valid_to - record.valid_from).days + 1):
            day = record.valid_from + timedelta(days=offset)
            days.append(FxDay(day, record.rate, record.source_reference))
    days.sort(key=lambda d: d.rate_date)  # stable: overlapping origins keep range order
    return days


def check_coverage(days: Sequence[FxDay], start: date = BACKFILL_FROM) -> None:
    """Require a continuous series from `start` to the last day, without gaps or overlaps."""
    if not days:
        raise CoverageError("No daily rates to check")
    first = days[0]
    if first.rate_date != start:
        raise CoverageError(
            f"Series starts on {first.rate_date} ({first.source_reference}), expected {start}"
        )
    for prev, cur in zip(days, days[1:], strict=False):
        if cur.rate_date == prev.rate_date:
            raise CoverageError(
                f"Overlap on {cur.rate_date}: {prev.source_reference} and {cur.source_reference}"
            )
        expected = prev.rate_date + timedelta(days=1)
        if cur.rate_date != expected:
            raise CoverageError(
                f"Gap: no rate for {expected} (until {cur.rate_date - timedelta(days=1)}); "
                f"between {prev.source_reference} and {cur.source_reference}"
            )


def max_range_days(state: Mapping[date, TrmRecord]) -> int:
    """Length in days (inclusive) of the longest validity range; 0 for an empty state."""
    return max(((r.valid_to - r.valid_from).days + 1 for r in state.values()), default=0)

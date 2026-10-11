"""Pure tests for pits.sources.trm.replay."""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from trm_helpers import B1, B2, B3, B4, Reader, day_records, make_batch, rec

from pits.sources.trm.contract import BACKFILL_FROM
from pits.sources.trm.parse import TrmDataError, parse_page
from pits.sources.trm.replay import (
    CoverageError,
    ReplayError,
    check_coverage,
    expand_daily,
    max_range_days,
    reconstruct,
    select_inputs,
)

D1 = date(2026, 10, 1)


def replay(batches, data):
    plan = select_inputs(batches)
    return plan, reconstruct(plan, Reader(data))


def rates(state):
    return {k: str(v.rate) for k, v in sorted(state.items())}


def test_full_then_incremental_then_since_correction_since_wins():
    full = day_records(D1, 5, "100", "f")  # Oct 1..5
    inc = day_records(date(2026, 10, 6), 2, "200", "i")  # Oct 6..7
    since = day_records(date(2026, 10, 5), 3, "300", "s")  # corrects Oct 5, redoes 6, 7
    batches = [
        make_batch(B1, date(2026, 10, 8), "full", full),
        make_batch(B2, date(2026, 10, 9), "incremental", inc, from_exclusive=date(2026, 10, 5)),
        make_batch(B3, date(2026, 10, 10), "since", since, from_exclusive=date(2026, 10, 4)),
    ]
    plan, state = replay(batches, {B1: full, B2: inc, B3: since})
    assert plan.baseline.batch_id == B1
    assert [m.batch_id for m in plan.inputs] == [B1, B2, B3]
    assert rates(state) == {
        date(2026, 10, 1): "100",
        date(2026, 10, 2): "100",
        date(2026, 10, 3): "100",
        date(2026, 10, 4): "100",
        date(2026, 10, 5): "300",
        date(2026, 10, 6): "300",
        date(2026, 10, 7): "300",
    }


def test_later_shorter_full_does_not_resurrect_old_rows():
    old = day_records(D1, 5, "100", "o")
    new = day_records(D1, 3, "150", "n")
    batches = [
        make_batch(B1, date(2026, 10, 8), "full", old),
        make_batch(B2, date(2026, 10, 9), "full", new),
    ]
    plan, state = replay(batches, {B1: old, B2: new})
    assert plan.baseline.batch_id == B2 and len(plan.inputs) == 1
    assert rates(state) == {D1 + timedelta(days=i): "150" for i in range(3)}


def test_empty_incremental_is_noop():
    full = day_records(D1, 3, "100", "f")
    batches = [
        make_batch(B1, date(2026, 10, 8), "full", full),
        make_batch(B2, date(2026, 10, 9), "incremental", [], from_exclusive=date(2026, 10, 3)),
    ]
    _, state = replay(batches, {B1: full, B2: []})
    assert rates(state) == {D1 + timedelta(days=i): "100" for i in range(3)}


def test_empty_since_that_deletes_rows_fails_with_batch_start_and_first_deleted():
    full = [rec(BACKFILL_FROM, date(2026, 10, 3), "100", "f#row=0")]
    full += [rec(date(2026, 10, 4), date(2026, 10, 6), "110", "f#row=1")]
    batches = [
        make_batch(B1, date(2026, 10, 8), "full", full),
        make_batch(B2, date(2026, 10, 9), "since", [], from_exclusive=date(2026, 10, 3)),
    ]
    with pytest.raises(CoverageError) as err:
        replay(batches, {B1: full, B2: []})
    text = str(err.value)
    assert B2 in text and "2026-10-04" in text and "f#row=1" in text


def test_empty_since_that_deletes_nothing_is_a_valid_noop():
    full = day_records(D1, 3, "100", "f")
    batches = [
        make_batch(B1, date(2026, 10, 8), "full", full),
        make_batch(B2, date(2026, 10, 9), "since", [], from_exclusive=date(2026, 10, 10)),
    ]
    _, state = replay(batches, {B1: full, B2: []})
    assert rates(state) == {D1 + timedelta(days=i): "100" for i in range(3)}


def test_incremental_after_since_starts_from_the_since_watermark():
    full = day_records(D1, 5, "100", "f")  # Oct 1..5
    since = day_records(date(2026, 10, 4), 3, "300", "s")  # Oct 4..6
    inc = day_records(date(2026, 10, 7), 1, "400", "i")  # Oct 7
    batches = [
        make_batch(B1, date(2026, 10, 8), "full", full),
        make_batch(B2, date(2026, 10, 9), "since", since, from_exclusive=date(2026, 10, 3)),
        make_batch(B3, date(2026, 10, 10), "incremental", inc, from_exclusive=date(2026, 10, 6)),
    ]
    _, state = replay(batches, {B1: full, B2: since, B3: inc})
    assert [str(v.rate) for _, v in sorted(state.items())] == [
        "100",
        "100",
        "100",
        "300",
        "300",
        "300",
        "400",
    ]


def test_since_at_backfill_start_with_rows_equals_a_full():
    full = day_records(date(2026, 10, 1), 3, "100", "f")
    since = day_records(BACKFILL_FROM, 2, "500", "s")
    batches = [
        make_batch(B1, date(2026, 10, 8), "full", full),
        make_batch(
            B2,
            date(2026, 10, 9),
            "since",
            since,
            from_exclusive=BACKFILL_FROM - timedelta(days=1),
        ),
    ]
    _, state = replay(batches, {B1: full, B2: since})
    assert state == {r.valid_from: r for r in since}


def test_since_before_all_state_replaces_everything_from_there():
    full = day_records(D1, 3, "100", "f")
    since = day_records(date(2026, 9, 29), 2, "200", "s")
    batches = [
        make_batch(B1, date(2026, 10, 8), "full", full),
        make_batch(B2, date(2026, 10, 9), "since", since, from_exclusive=date(2026, 9, 28)),
    ]
    _, state = replay(batches, {B1: full, B2: since})
    assert state == {r.valid_from: r for r in since}


def test_same_day_tie_break_by_finished_at_then_batch_id():
    day = date(2026, 10, 9)
    early = datetime(2026, 10, 9, 12, tzinfo=UTC)
    full_a = day_records(D1, 2, "100", "a")
    full_b = day_records(D1, 2, "200", "b")
    # later finished_at wins even if its batch_id sorts first
    batches = [
        make_batch(B2, day, "full", full_a, finished_at=early),
        make_batch(B1, day, "full", full_b, finished_at=early + timedelta(hours=1)),
    ]
    plan, state = replay(batches, {B2: full_a, B1: full_b})
    assert plan.baseline.batch_id == B1 and rates(state)[D1] == "200"
    # identical finished_at: batch_id decides
    tie = [make_batch(B1, day, "full", full_a), make_batch(B2, day, "full", full_b)]
    plan, _ = replay(tie, {B1: full_a, B2: full_b})
    assert plan.baseline.batch_id == B2


def test_input_order_does_not_change_result():
    full = day_records(D1, 5, "100", "f")
    inc = day_records(date(2026, 10, 6), 2, "200", "i")
    batches = [
        make_batch(B1, date(2026, 10, 8), "full", full),
        make_batch(B2, date(2026, 10, 9), "incremental", inc, from_exclusive=date(2026, 10, 5)),
        make_batch(B3, date(2026, 10, 10), "incremental", [], from_exclusive=date(2026, 10, 7)),
    ]
    data = {B1: full, B2: inc, B3: []}
    expected = replay(batches, data)[1]
    for seed in range(5):
        shuffled = batches[:]
        random.Random(seed).shuffle(shuffled)
        assert replay(shuffled, data)[1] == expected


def test_pages_out_of_order_within_a_batch_fail():
    full = day_records(D1, 4, "100", "f")
    manifest = make_batch(B1, date(2026, 10, 8), "full", full)
    out_of_order = [full[2], full[3], full[0], full[1]]  # pages 2,1 swapped
    with pytest.raises(ReplayError, match="out of order"):
        reconstruct(select_inputs([manifest]), Reader({B1: out_of_order}))


def test_no_full_batch_fails():
    inc = day_records(D1, 2)
    manifest = make_batch(B1, date(2026, 10, 8), "incremental", inc, from_exclusive=D1)
    with pytest.raises(ReplayError, match="full"):
        select_inputs([manifest])
    with pytest.raises(ReplayError, match="full"):
        select_inputs([])


def test_row_count_mismatch_with_manifest_fails():
    full = day_records(D1, 3)
    manifest = make_batch(B1, date(2026, 10, 8), "full", full)
    with pytest.raises(ReplayError, match="manifest says"):
        reconstruct(select_inputs([manifest]), Reader({B1: full[:2]}))


def test_incremental_row_not_after_watermark_fails():
    full = day_records(D1, 3)
    bad = day_records(date(2026, 10, 3), 2, tag="i")
    batches = [
        make_batch(B1, date(2026, 10, 8), "full", full),
        make_batch(B2, date(2026, 10, 9), "incremental", bad, from_exclusive=date(2026, 10, 3)),
    ]
    with pytest.raises(ReplayError, match="not after the watermark"):
        replay(batches, {B1: full, B2: bad})


def test_since_row_before_start_fails():
    full = day_records(D1, 3)
    bad = day_records(date(2026, 10, 2), 2, tag="s")
    batches = [
        make_batch(B1, date(2026, 10, 8), "full", full),
        make_batch(B2, date(2026, 10, 9), "since", bad, from_exclusive=date(2026, 10, 2)),
    ]
    with pytest.raises(ReplayError, match="before since"):
        replay(batches, {B1: full, B2: bad})


def test_expand_range_is_inclusive_and_covers_weekend():
    state = {date(2026, 10, 10): rec(date(2026, 10, 10), date(2026, 10, 13), "3194.44", "k#row=7")}
    days = expand_daily(state)
    assert [d.rate_date for d in days] == [date(2026, 10, 10) + timedelta(days=i) for i in range(4)]
    assert {d.rate for d in days} == {Decimal("3194.44")}
    assert {d.source_reference for d in days} == {"k#row=7"}
    assert date(2026, 10, 10).weekday() == 5  # Saturday: published rows span weekends
    assert max_range_days(state) == 4


def test_single_day_range():
    state = {D1: rec(D1)}
    assert [d.rate_date for d in expand_daily(state)] == [D1]
    assert max_range_days(state) == 1
    assert max_range_days({}) == 0


def test_future_ranges_are_expanded_without_clock():
    far = date(2099, 1, 1)
    assert [d.rate_date for d in expand_daily({far: rec(far, far + timedelta(days=2))})][-1] == (
        far + timedelta(days=2)
    )


def series(*ranges):
    return {a: rec(a, b, ref=f"k#row={i}") for i, (a, b) in enumerate(ranges)}


def test_coverage_ok_when_continuous_from_backfill():
    state = series((BACKFILL_FROM, date(1991, 12, 5)), (date(1991, 12, 6), date(1991, 12, 6)))
    check_coverage(expand_daily(state))


def test_coverage_first_date_must_be_backfill_start():
    state = series((date(1991, 12, 3), date(1991, 12, 5)))
    with pytest.raises(CoverageError, match="starts on 1991-12-03.*expected 1991-12-02"):
        check_coverage(expand_daily(state))


def test_coverage_gap_reports_missing_date_and_neighbors():
    state = series((BACKFILL_FROM, date(1991, 12, 5)), (date(1991, 12, 8), date(1991, 12, 9)))
    with pytest.raises(CoverageError, match=r"no rate for 1991-12-06.*k#row=0.*k#row=1"):
        check_coverage(expand_daily(state))


def test_coverage_overlap_reports_both_origins():
    state = series((BACKFILL_FROM, date(1991, 12, 5)), (date(1991, 12, 4), date(1991, 12, 8)))
    with pytest.raises(CoverageError, match=r"Overlap on 1991-12-04.*k#row=0.*k#row=1"):
        check_coverage(expand_daily(state))


def test_errors_are_trm_data_errors():
    assert issubclass(ReplayError, TrmDataError) and issubclass(CoverageError, TrmDataError)


def test_end_to_end_parse_then_replay_rows():
    rows = [
        {
            "valor": "3194.44",
            "unidad": "COP",
            "vigenciadesde": "1991-12-02T00:00:00.000",
            "vigenciahasta": "1991-12-04T00:00:00.000",
        }
    ]
    records = parse_page(rows, page_key="p")
    manifest = make_batch(B4, date(2026, 10, 10), "full", records)
    state = reconstruct(select_inputs([manifest]), Reader({B4: records}))
    days = expand_daily(state)
    check_coverage(days)
    assert [d.source_reference for d in days] == ["p#row=0"] * 3

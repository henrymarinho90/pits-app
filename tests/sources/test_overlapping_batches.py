"""D106: no lock between runs; overlapping batches must normalize to the same logical rows.

Offline evidence (MemoryRawStore only): two incremental TRM batches with the same rows give the
same (rate_date, rate) as one, and two RUNT batches of one publication resolve to the last one with
equal rows (source_reference aside). Batch ids, finished_at and LIST order are deliberately out of
order with each other (lesson 92).
"""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta

from runt_support import B1 as R1
from runt_support import B2 as R2
from runt_support import B3 as R3
from runt_support import put_runt_batch, raw_row
from trm_helpers import B1, B2, B3, put_raw_batch
from trm_helpers import raw_row as trm_row

from pits.ingestion.raw_store import MemoryRawStore
from pits.sources.runt.normalize import normalize_runt
from pits.sources.trm.contract import BACKFILL_FROM
from pits.sources.trm.normalize import normalize_trm


class RandomOrderStore(MemoryRawStore):
    def __init__(self, seed: int) -> None:
        super().__init__()
        self.rng = random.Random(seed)

    def list_prefixes(self, prefix):
        found = super().list_prefixes(prefix)
        self.rng.shuffle(found)
        return found


def _trm_full(store) -> None:
    put_raw_batch(
        store,
        B1,
        date(2026, 10, 8),
        "full",
        [
            trm_row(BACKFILL_FROM, date(2026, 10, 9), "3000.5"),
            trm_row(date(2026, 10, 10), date(2026, 10, 10), "3194.44"),
        ],
    )


INCREMENTAL_ROWS = [
    trm_row(date(2026, 10, 11), date(2026, 10, 11), "3200"),
    trm_row(date(2026, 10, 12), date(2026, 10, 13), "3250.75"),
]


def _trm_incremental(store, batch_id: str, finished_at: datetime) -> None:
    put_raw_batch(
        store,
        batch_id,
        date(2026, 10, 9),
        "incremental",
        INCREMENTAL_ROWS,
        from_exclusive=date(2026, 10, 10),
        finished_at=finished_at,
    )


def _trm_rate_rows(norm, result) -> list[tuple[str, str]]:
    lines = norm.get(result.csv_key).decode().rstrip("\n").split("\n")[1:]
    return [(f[0], f[3]) for f in (line.split(",") for line in lines)]


def test_trm_two_incremental_batches_with_same_rows_equal_a_single_one():
    early = datetime(2026, 10, 9, 13, tzinfo=UTC)

    single = MemoryRawStore()
    _trm_full(single)
    _trm_incremental(single, B2, early)
    one_norm = MemoryRawStore()
    one = normalize_trm(single, one_norm, raw_bucket="pits-raw")
    expected = _trm_rate_rows(one_norm, one)

    for store in (MemoryRawStore(), RandomOrderStore(1), RandomOrderStore(2)):
        _trm_full(store)
        # B3 sorts after B2 but finished earlier; B2 is the last committed (two out-of-order items).
        _trm_incremental(store, B3, early)
        _trm_incremental(store, B2, early + timedelta(hours=1))
        norm = MemoryRawStore()
        both = normalize_trm(store, norm, raw_bucket="pits-raw")
        assert both.inputs == 3
        assert _trm_rate_rows(norm, both) == expected


def _runt_rows(norm, result_manifest_prefix_key: str) -> list[str]:
    prefix = result_manifest_prefix_key.removesuffix("manifest.json")
    parts = sorted(k for k in norm.objects if k.startswith(prefix) and k.endswith(".csv"))
    lines: list[str] = []
    for key in parts:
        lines.extend(norm.get(key).decode().rstrip("\n").split("\n")[1:])
    # source_reference is the last column and legitimately differs between batches.
    return [line.rsplit(",", 1)[0] for line in lines]


def test_runt_two_batches_of_same_publication_resolve_to_last_with_equal_rows():
    rows = [raw_row(i, cantidad=str(i + 1)) for i in range(5)]
    shuffled = [rows[3], rows[0], rows[4], rows[2], rows[1]]

    only_last = MemoryRawStore()
    put_runt_batch(only_last, R2, date(2026, 10, 12), shuffled)
    single_norm = MemoryRawStore()
    (single,) = normalize_runt(only_last, single_norm, raw_bucket="pits-raw")
    expected = _runt_rows(single_norm, single.manifest_key)
    assert len(expected) == 5

    for store in (MemoryRawStore(), RandomOrderStore(1), RandomOrderStore(2)):
        # Written newest first, with a third batch (same day as R1, greater id) in between.
        put_runt_batch(store, R2, date(2026, 10, 12), shuffled)
        put_runt_batch(store, R3, date(2026, 10, 11), list(reversed(rows)))
        put_runt_batch(store, R1, date(2026, 10, 11), rows)
        norm = MemoryRawStore()
        (result,) = normalize_runt(store, norm, raw_bucket="pits-raw")
        assert result.batch_id == R2 and result.inputs == 1
        assert _runt_rows(norm, result.manifest_key) == expected

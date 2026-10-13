"""Builders of real vehicle_fleet_snapshot artifacts for the load tests (not a test module).

The artifacts are written by the real `normalize_runt` from raw batches built with runt_support,
so the loader tests exercise the exact bytes the normalizer produces.
"""

from __future__ import annotations

from datetime import date

from runt_support import B1, B2, B3, big_rows, put_runt_batch, raw_row

from pits.ingestion.raw_store import MemoryRawStore
from pits.sources.runt.normalize import FleetResult, normalize_runt

RAW_BUCKET = "pits-raw"
DAY = date(2026, 10, 12)
LATER_DAY = date(2026, 10, 20)

# Values that stress ordering and quoting: accents, case, comma and quote, digits vs letters.
TRICKY_NAMES = ["ÑANDÚ", "bogotá", "BOGOTÁ", "Z", "a", "MUNI, X", 'A "Q" B', "9 DE JULIO", "ÁNGEL"]


def tricky_rows(*, year: int, month: int) -> list[dict[str, str]]:
    return [
        raw_row(i, year=year, month=month, nombre_municipio=name, cantidad=str(1 + i))
        for i, name in enumerate(TRICKY_NAMES)
    ]


def build_raw_and_normalized(
    *, big: int = 25, small_publication: tuple[int, int] = (2026, 10)
) -> tuple[MemoryRawStore, MemoryRawStore, dict[str, FleetResult]]:
    """Two publications: 2026-09 with `big` rows and `small_publication` with tricky rows."""
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_runt_batch(raw, B1, DAY, big_rows(big, year=2026, month=9), year=2026, month=9, page_size=7)
    year, month = small_publication
    put_runt_batch(raw, B2, DAY, tricky_rows(year=year, month=month), year=year, month=month)
    results = {r.publication: r for r in normalize_runt(raw, norm, raw_bucket=RAW_BUCKET)}
    return raw, norm, results


def add_newer_batch(
    raw: MemoryRawStore,
    norm: MemoryRawStore,
    publication: tuple[int, int],
    rows: list[dict[str, str]],
) -> FleetResult:
    """A later batch of one publication (it wins over the previous one) and its artifact."""
    year, month = publication
    put_runt_batch(raw, B3, LATER_DAY, rows, year=year, month=month)
    label = f"{year:04d}-{month:02d}"
    return next(
        r for r in normalize_runt(raw, norm, raw_bucket=RAW_BUCKET) if r.publication == label
    )


def drop_artifact(store: MemoryRawStore, fingerprint: str) -> None:
    for key in [k for k in store.objects if f"fingerprint={fingerprint}/" in k]:
        del store.objects[key]

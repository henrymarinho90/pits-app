"""Builders of real regional_fleet_brand artifacts for the load tests (not a test module).

The artifacts are written by the real `normalize_brand_fleet` from raw batches built with
brand_fleet_support, so the loader tests exercise the exact bytes the normalizer produces.
All data is synthetic.
"""

from __future__ import annotations

from datetime import date

from brand_fleet_support import (
    B1,
    B2,
    BOYACA,
    RISARALDA,
    ROWS_UPDATED_AT,
    boyaca_row,
    put_brand_batch,
    risaralda_row,
)

from pits.ingestion.raw_store import MemoryRawStore
from pits.sources.brand_fleet.contract import BrandFleetSource
from pits.sources.brand_fleet.normalize import BrandFleetResult, normalize_brand_fleet

RAW_BUCKET = "pits-raw"
DAY = date(2026, 10, 14)
LATER_DAY = date(2026, 10, 20)


def boyaca_rows() -> list[dict[str, str]]:
    """Accents, a comma in a brand (quoted CSV), two services and statuses; 6 rows, 4 groups."""
    return [
        boyaca_row(0, clase="AUTOMOVIL", marca="MARCA ÁX", linea="LÍNEA 1"),
        boyaca_row(1, clase="AUTOMOVIL", marca="MARCA ÁX", linea="LÍNEA 1"),
        boyaca_row(2, clase="AUTOMOVIL", marca="MARCA ÁX", linea="LÍNEA 1", servicio="PUBLICO"),
        boyaca_row(3, clase="MOTOCICLETA", marca="MARCA, Y", linea="L2", estado="CANCELADO"),
        boyaca_row(4, clase="MOTOCICLETA", marca="MARCA, Y", linea="L2", estado="CANCELADO"),
        boyaca_row(5, clase="CAMIONETA", marca="MARCA Z", linea="L3"),
    ]


def risaralda_rows() -> list[dict[str, str]]:
    """No service/status published: NULL in landing; 5 rows, 3 groups."""
    return [
        risaralda_row(0, clase="MOTOCICLETA", marca="VICTORY", linea="ONE"),
        risaralda_row(1, clase="MOTOCICLETA", marca="VICTORY", linea="ONE"),
        risaralda_row(2, clase="MOTOCICLETA", marca="VICTORY", linea="ONE"),
        risaralda_row(3, clase="AUTOMOVIL", marca="MARCA W", linea="W1"),
        risaralda_row(4, clase="AUTOMOVIL", marca="MARCA W", linea="W2"),
    ]


def build_raw_and_normalized() -> tuple[
    MemoryRawStore, MemoryRawStore, dict[str, BrandFleetResult]
]:
    """Both sources committed and normalized into the same stores."""
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_brand_batch(raw, BOYACA, B1, DAY, boyaca_rows())
    put_brand_batch(raw, RISARALDA, B1, DAY, risaralda_rows())
    results = {
        s.key: normalize_brand_fleet(raw, norm, s, raw_bucket=RAW_BUCKET)
        for s in (BOYACA, RISARALDA)
    }
    return raw, norm, results


def add_newer_batch(
    raw: MemoryRawStore,
    norm: MemoryRawStore,
    source: BrandFleetSource,
    data: list[dict[str, str]],
) -> BrandFleetResult:
    """A later batch of `source` (it wins over the previous one) + its artifact."""
    put_brand_batch(raw, source, B2, LATER_DAY, data, updated_at=ROWS_UPDATED_AT + 86400 * 100)
    return normalize_brand_fleet(raw, norm, source, raw_bucket=RAW_BUCKET)


def drop_artifact(store: MemoryRawStore, fingerprint: str) -> None:
    for key in [k for k in store.objects if f"fingerprint={fingerprint}/" in k]:
        del store.objects[key]

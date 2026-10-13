"""Builders of real divipola_municipality artifacts for the load tests (not a test module).

The artifacts are written by the real `normalize_divipola` from raw batches built with
divipola_support, so the loader tests exercise the exact bytes the normalizer produces.
"""

from __future__ import annotations

from datetime import date

from divipola_support import B1, B2, ROWS_UPDATED_AT, put_divipola_batch, raw_row

from pits.ingestion.raw_store import MemoryRawStore
from pits.sources.divipola.normalize import DivipolaResult, normalize_divipola

RAW_BUCKET = "pits-raw"
DAY = date(2026, 10, 13)
LATER_DAY = date(2026, 10, 20)


def realistic_rows() -> list[dict[str, str]]:
    """Accents, a comma in names (quoted CSV), a decimal comma, other types and departments."""
    return [
        raw_row(0, cod_mpio="05001", nom_mpio="MEDELLÍN"),
        raw_row(
            1, cod_mpio="05002", nom_mpio="ABEJORRAL", longitud="-75,428739", latitud="5,789315"
        ),
        raw_row(
            2,
            cod_dpto="11",
            dpto="BOGOTÁ, D.C.",
            cod_mpio="11001",
            nom_mpio="BOGOTÁ, D.C.",
            longitud="-74,106992",
            latitud="4,649251",
        ),
        raw_row(
            3,
            cod_dpto="88",
            dpto="ARCHIPIÉLAGO DE SAN ANDRÉS, PROVIDENCIA Y SANTA CATALINA",
            cod_mpio="88001",
            nom_mpio="SAN ANDRÉS",
            tipo_municipio="Isla",
            longitud="-81,707181",
            latitud="12,578108",
        ),
        raw_row(
            4,
            cod_dpto="91",
            dpto="AMAZONAS",
            cod_mpio="91263",
            nom_mpio="EL ENCANTO",
            tipo_municipio="Área no municipalizada",
            longitud="-73,2",
            latitud="-1,7",
        ),
    ]


def build_raw_and_normalized(
    data: list[dict[str, str]] | None = None,
) -> tuple[MemoryRawStore, MemoryRawStore, DivipolaResult]:
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_divipola_batch(raw, B1, DAY, data if data is not None else realistic_rows())
    return raw, norm, normalize_divipola(raw, norm, raw_bucket=RAW_BUCKET)


def add_newer_batch(
    raw: MemoryRawStore, norm: MemoryRawStore, data: list[dict[str, str]]
) -> DivipolaResult:
    """A later batch (it wins over the previous one, with a newer rowsUpdatedAt) + its artifact."""
    put_divipola_batch(raw, B2, LATER_DAY, data, updated_at=ROWS_UPDATED_AT + 86400 * 100)
    return normalize_divipola(raw, norm, raw_bucket=RAW_BUCKET)


def drop_artifact(store: MemoryRawStore, fingerprint: str) -> None:
    for key in [k for k in store.objects if f"fingerprint={fingerprint}/" in k]:
        del store.objects[key]

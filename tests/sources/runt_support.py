"""Shared RUNT raw-batch builders for normalize tests (not a test module; no test_ prefix)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, date, datetime

from pits.ingestion.manifest import (
    Extractor,
    FileEntry,
    Manifest,
    Query,
    Watermark,
    manifest_key,
    sha256_hex,
)
from pits.ingestion.raw_store import RawStore, batch_prefix
from pits.sources.runt.contract import (
    ATTRIBUTION,
    DATASET_ID,
    EXPECTED_SCHEMA,
    LICENSE,
    SOURCE_SYSTEM,
    SOURCE_URL,
    WATERMARK_COLUMN,
)

B1 = "0b6f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a10"
B2 = "1c7a7d2f-4d2b-4a1f-8b62-3e5d7a9fab21"
B3 = "2d8b8e30-5e3c-4b20-9c73-4f6e8bafbc32"
MONTH_LABELS = [
    "ENERO",
    "FEBRERO",
    "MARZO",
    "ABRIL",
    "MAYO",
    "JUNIO",
    "JULIO",
    "AGOSTO",
    "SEPTIEMBRE",
    "OCTUBRE",
    "NOVIEMBRE",
    "DICIEMBRE",
]


def raw_row(i: int = 0, *, year: int = 2026, month: int = 10, **over: str) -> dict[str, str]:
    """One valid RUNT row; every i gives a distinct primary key."""
    base = {
        "nombre_departamento": "ANTIOQUIA",
        "nombre_municipio": f"MUNI{i:06d}",
        "nombre_servicio": "PARTICULAR",
        "estado_del_vehiculo": "ACTIVO",
        "nombre_de_la_clase": "CAMPERO",
        "fecha_de_registro": "1999",
        "cantidad": "3",
        "mes_de_publicacion": MONTH_LABELS[month - 1],
        "a_o_de_publicacion": str(year),
    }
    return {**base, **over}


def put_runt_batch(
    store: RawStore,
    batch_id: str,
    day: date,
    rows: Sequence[dict[str, str]],
    *,
    year: int = 2026,
    month: int = 10,
    page_size: int = 3,
) -> Manifest:
    """Write payload pages + manifest like the extractor would (a committed full snapshot)."""
    prefix = batch_prefix(SOURCE_SYSTEM, day, batch_id)
    files: list[FileEntry] = []
    offset = 0
    for start in range(0, len(rows), page_size):
        page = rows[start : start + page_size]
        body = json.dumps(page, ensure_ascii=False).encode("utf-8")
        key = f"{prefix}payload-{len(files):05d}.json"
        store.put_once(key, body, "application/json")
        files.append(
            FileEntry(key, offset, len(page), len(body), sha256_hex(body), "application/json")
        )
        offset += len(page)
    started = datetime(day.year, day.month, day.day, 12, tzinfo=UTC)
    manifest = Manifest(
        source_system=SOURCE_SYSTEM,
        dataset_id=DATASET_ID,
        source_url=SOURCE_URL,
        license=LICENSE,
        attribution=ATTRIBUTION,
        batch_id=batch_id,
        extraction_date=day,
        started_at=started,
        finished_at=started,
        extractor=Extractor("pits.sources.runt", "test"),
        source_rows_updated_at=1,
        app_token_used=False,
        query=Query(":id ASC", page_size, None),
        watermark=Watermark(WATERMARK_COLUMN, "full", None, date(year, month, 1)),
        schema=EXPECTED_SCHEMA,
        row_count=offset,
        files=tuple(files),
    )
    store.put_once(manifest_key(prefix), manifest.to_json(), "application/json")
    return manifest


def big_rows(n: int, *, year: int = 2026, month: int = 10) -> list[dict[str, str]]:
    """n rows with distinct primary keys (coprime moduli) and realistic repeated values."""
    return [
        raw_row(
            i,
            year=year,
            month=month,
            nombre_departamento=f"DEPARTAMENTO {i % 32}",
            nombre_municipio=f"MUNICIPIO {i % 288}",
            nombre_servicio=f"SERVICIO {i % 5}",
            estado_del_vehiculo=f"ESTADO {i % 2}",
            nombre_de_la_clase=f"CLASE {i % 99}",
            fecha_de_registro=str(1900 + i % 127),
            cantidad=str(1 + i % 40),
        )
        for i in range(n)
    ]

"""Source contract for the RUNT fleet snapshot (verified on the live API 2026-10-12, D96)."""

from __future__ import annotations

from pits.ingestion.manifest import SchemaColumn

SOURCE_SYSTEM = "mintransporte_runt_parque"
DATASET_ID = "u3vn-bdcy"
SOURCE_URL = "https://www.datos.gov.co/resource/u3vn-bdcy.json"
LICENSE = "CC_40_BY_SA"
ATTRIBUTION = "Ministerio de Transporte - MinTransporte, Bogotá D.C."

# Non-system columns, in the order reported by the metadata endpoint. Every value arrives as a
# JSON string, including the number columns.
EXPECTED_SCHEMA = (
    SchemaColumn("nombre_departamento", "text"),
    SchemaColumn("nombre_municipio", "text"),
    SchemaColumn("nombre_servicio", "text"),
    SchemaColumn("estado_del_vehiculo", "text"),
    SchemaColumn("nombre_de_la_clase", "text"),
    SchemaColumn("fecha_de_registro", "number"),
    SchemaColumn("cantidad", "number"),
    SchemaColumn("mes_de_publicacion", "text"),
    SchemaColumn("a_o_de_publicacion", "number"),
)
EXPECTED_COLUMNS = frozenset(c.name for c in EXPECTED_SCHEMA)

YEAR_COLUMN = "a_o_de_publicacion"
MONTH_COLUMN = "mes_de_publicacion"
# Manifest v1 reuse: the snapshot has no watermark; the column field documents the publication.
WATERMARK_COLUMN = f"{YEAR_COLUMN},{MONTH_COLUMN}"
ORDER = ":id ASC"
PAGE_SIZE = 5000
MAX_PAGE_BYTES = 8 * 1024 * 1024  # D65/D75 single-object limit

MONTHS = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}

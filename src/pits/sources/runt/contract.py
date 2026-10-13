"""Source contract for the RUNT fleet snapshot (verified on the live API 2026-10-12, D96)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

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

MIN_REGISTRATION_YEAR = 1900  # aligned with the CHECK of landing.vehicle_fleet_snapshot (D99, D103)
_INT_RE = re.compile(r"[0-9]+")
_YEAR_RE = re.compile(r"[0-9]{4}")
# Unicode category Cc is exactly these 65 code points (C0, DEL and C1); a precompiled class is
# much faster than unicodedata.category per character on ~190k rows x 9 values. A test compares
# it against unicodedata over the whole code point range.
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


class RowError(ValueError):
    """A raw row violates the contract. `field` is the column (None: the whole row) and `problem`
    never contains data, so callers can prefix their own reference (page, row index)."""

    def __init__(self, field: str | None, problem: str) -> None:
        super().__init__(problem if field is None else f"{field} {problem}")
        self.field = field
        self.problem = problem

    def at(self, ref: str) -> str:
        """Message with the caller's row reference: 'ref.field problem' or 'ref problem'."""
        return (
            f"{ref} {self.problem}" if self.field is None else f"{ref}.{self.field} {self.problem}"
        )


def validate_row(row: Mapping[str, Any], publication: tuple[int, int]) -> None:
    """Row-level rules shared by the extractor and the normalizer (D96, D97, D103); RowError if
    one fails. Exact keys; string values without control characters (Unicode Cc, NUL included);
    cantidad an integer >= 1; fecha_de_registro a 4-digit year in [1900, publication year];
    publication (year, month) equal to `publication`."""
    if set(row) != EXPECTED_COLUMNS:
        raise RowError(
            None,
            f"has wrong keys (missing={sorted(EXPECTED_COLUMNS - set(row))}, "
            f"unexpected_count={len(set(row) - EXPECTED_COLUMNS)})",
        )
    for name, value in row.items():
        if not isinstance(value, str):
            raise RowError(name, "must be a string")
        if CONTROL_RE.search(value):
            raise RowError(name, "contains a control character")
    cantidad = row["cantidad"]
    if not _INT_RE.fullmatch(cantidad) or int(cantidad) < 1:
        raise RowError("cantidad", "is not an integer >= 1")
    year_text, month_text = row[YEAR_COLUMN], row[MONTH_COLUMN]
    if not _YEAR_RE.fullmatch(year_text) or month_text not in MONTHS:
        raise RowError(None, "has an invalid publication (not a 4-digit year or a known month)")
    if (int(year_text), MONTHS[month_text]) != publication:
        raise RowError(
            None, f"belongs to another publication than {publication[0]:04d}-{publication[1]:02d}"
        )
    registration = row["fecha_de_registro"]
    if (
        not _YEAR_RE.fullmatch(registration)
        or not MIN_REGISTRATION_YEAR <= int(registration) <= publication[0]
    ):
        raise RowError(
            "fecha_de_registro",
            f"is not a 4-digit year between {MIN_REGISTRATION_YEAR} and the publication year",
        )

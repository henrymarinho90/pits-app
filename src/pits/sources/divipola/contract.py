"""Source contract for DIVIPOLA municipality codes (verified on the live API 2026-10-13, D122)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pits.ingestion.manifest import SchemaColumn

SOURCE_SYSTEM = "dane_divipola"
DATASET_ID = "gdxc-w37w"
SOURCE_URL = "https://www.datos.gov.co/resource/gdxc-w37w.json"
LICENSE = "CC_40_BY_SA"
ATTRIBUTION = "Departamento Administrativo Nacional de Estadística - DANE"

# Non-system columns in the order reported by the metadata endpoint. Every value is a string,
# coordinates included (they use a decimal comma: "-74,106992").
EXPECTED_SCHEMA = (
    SchemaColumn("cod_dpto", "text"),
    SchemaColumn("dpto", "text"),
    SchemaColumn("cod_mpio", "text"),
    SchemaColumn("nom_mpio", "text"),
    SchemaColumn("tipo_municipio", "text"),
    SchemaColumn("longitud", "text"),
    SchemaColumn("latitud", "text"),
)
EXPECTED_COLUMNS = frozenset(c.name for c in EXPECTED_SCHEMA)

# The source has no cut-off column (the 2024-12-30 cut-off lives only in the description), so the
# watermark documents rowsUpdatedAt, which is deterministic and changes with the rows (D122).
WATERMARK_COLUMN = "rowsUpdatedAt"
ORDER = ":id ASC"
PAGE_SIZE = 5000
MAX_PAGE_BYTES = 8 * 1024 * 1024  # D65/D75 single-object limit

MUNICIPALITY_TYPES = frozenset({"Municipio", "Isla", "Área no municipalizada"})

_DEPARTMENT_CODE_RE = re.compile(r"[0-9]{2}")
_MUNICIPALITY_CODE_RE = re.compile(r"[0-9]{5}")
_COORDINATE_RE = re.compile(r"-?[0-9]{1,3},[0-9]{1,8}")
# Unicode category Cc is exactly these 65 code points (C0, DEL and C1), as in the RUNT contract.
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


class RowError(ValueError):
    """A raw row violates the contract. `field` is the column (None: the whole row); `problem`
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


def validate_row(row: Mapping[str, Any]) -> None:
    """Row-level rules shared by the extractor and the normalizer (D122); RowError if one fails.

    Exact keys; string values without control characters; cod_dpto two digits; cod_mpio five
    digits starting with cod_dpto; tipo_municipio one of the known types; longitud and latitud a
    decimal-comma number; dpto and nom_mpio not blank and without surrounding whitespace."""
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
    if not _DEPARTMENT_CODE_RE.fullmatch(row["cod_dpto"]):
        raise RowError("cod_dpto", "is not a 2-digit code")
    if not _MUNICIPALITY_CODE_RE.fullmatch(row["cod_mpio"]):
        raise RowError("cod_mpio", "is not a 5-digit code")
    if not row["cod_mpio"].startswith(row["cod_dpto"]):
        raise RowError("cod_mpio", "does not start with cod_dpto")
    if row["tipo_municipio"] not in MUNICIPALITY_TYPES:
        raise RowError("tipo_municipio", "is not a known municipality type")
    for name in ("longitud", "latitud"):
        if not _COORDINATE_RE.fullmatch(row[name]):
            raise RowError(name, "is not a decimal-comma number")
    for name in ("dpto", "nom_mpio"):
        value = row[name]
        if value == "" or value != value.strip():
            raise RowError(name, "is empty or has leading or trailing whitespace")

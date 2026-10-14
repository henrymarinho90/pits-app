"""Source contracts for the regional brand/line fleet datasets (verified live 2026-10-14, D136).

Two departmental SODA datasets: Boyaca (em3d-hmim, 18 columns) and Risaralda (x9pp-pcn5, 6
columns including the plate). Each source declares the columns the source publishes
(`source_schema`, checked against the metadata) and the columns the extractor asks for
(`requested_schema`, sent as $select and stored in Manifest.schema). Risaralda never requests
`placa` (D136): the plate is personal data that the project does not need, so it is never
downloaded; a row that carries it anyway is a permanent error before anything is written.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pits.ingestion.manifest import SchemaColumn
from pits.sources.divipola.contract import CONTROL_RE, RowError

__all__ = [
    "MAX_PAGE_BYTES",
    "ORDER",
    "PAGE_SIZE",
    "SOURCES",
    "WATERMARK_COLUMN",
    "BrandFleetSource",
    "BrandFleetSourceName",
    "RowError",
    "get_source",
    "validate_row",
]

WATERMARK_COLUMN = "rowsUpdatedAt"
ORDER = ":id ASC"
PAGE_SIZE = 5000
MAX_PAGE_BYTES = 8 * 1024 * 1024  # D65/D75 single-object limit
LICENSE = "CC_40_BY_SA"
FORBIDDEN_COLUMN = "placa"


class BrandFleetSourceName(StrEnum):
    """Values of the --source option of the extract, normalize and load commands."""

    boyaca = "boyaca"
    risaralda = "risaralda"


@dataclass(frozen=True)
class BrandFleetSource:
    key: str  # CLI value of --source
    source_system: str
    dataset_id: str
    attribution: str
    source_schema: tuple[SchemaColumn, ...]  # what the metadata endpoint must report
    requested_schema: tuple[SchemaColumn, ...]  # what is selected, stored and normalized
    required: frozenset[str]  # columns every row must carry (SODA omits null keys)

    def __post_init__(self) -> None:
        source_names = {c.name for c in self.source_schema}
        if not {c.name for c in self.requested_schema} <= source_names:
            raise ValueError("requested_schema must be a subset of source_schema")
        if not self.required <= {c.name for c in self.requested_schema}:
            raise ValueError("required columns must be requested")

    @property
    def source_url(self) -> str:
        return f"https://www.datos.gov.co/resource/{self.dataset_id}.json"

    @property
    def requested_columns(self) -> frozenset[str]:
        return frozenset(c.name for c in self.requested_schema)

    @property
    def select(self) -> str:
        """The $select of every page: REQUESTED_SCHEMA joined by comma."""
        return ",".join(c.name for c in self.requested_schema)


_BOYACA_SCHEMA = (
    SchemaColumn("n", "number"),
    SchemaColumn("motivo_ingreso", "text"),
    SchemaColumn("cod_dane", "number"),
    SchemaColumn("dane_mun", "number"),
    SchemaColumn("provincia", "text"),
    SchemaColumn("municipio", "text"),
    SchemaColumn("clase", "text"),
    SchemaColumn("marca", "text"),
    SchemaColumn("linea", "text"),
    SchemaColumn("modelo", "text"),
    SchemaColumn("carroceria", "text"),
    SchemaColumn("pasajeros", "text"),
    SchemaColumn("tonelaje", "text"),
    SchemaColumn("cilindraje", "text"),
    SchemaColumn("servicio", "text"),
    SchemaColumn("estado", "text"),
    SchemaColumn("blindaje", "text"),
    SchemaColumn("importado", "text"),
)
_RISARALDA_SCHEMA = (
    SchemaColumn("clase", "text"),
    SchemaColumn("placa", "text"),
    SchemaColumn("marca", "text"),
    SchemaColumn("modelo", "number"),
    SchemaColumn("linea", "text"),
    SchemaColumn("cilindraje", "number"),
)

SOURCES: Mapping[str, BrandFleetSource] = {
    "boyaca": BrandFleetSource(
        key="boyaca",
        source_system="gobernacion_boyaca_parque_automotor",
        dataset_id="em3d-hmim",
        attribution="Gobernación de Boyacá, Boyacá",
        source_schema=_BOYACA_SCHEMA,
        requested_schema=_BOYACA_SCHEMA,
        required=frozenset({"clase", "marca", "linea", "servicio", "estado"}),
    ),
    "risaralda": BrandFleetSource(
        key="risaralda",
        source_system="gobernacion_risaralda_parque_automotor",
        dataset_id="x9pp-pcn5",
        attribution="Gobernación de Risaralda, Risaralda",
        source_schema=_RISARALDA_SCHEMA,
        requested_schema=tuple(c for c in _RISARALDA_SCHEMA if c.name != FORBIDDEN_COLUMN),
        required=frozenset({"clase", "marca", "linea"}),
    ),
}


def get_source(key: str) -> BrandFleetSource:
    try:
        return SOURCES[key]
    except KeyError:
        raise ValueError(f"Unknown brand fleet source: {key!r}") from None


def validate_row(source: BrandFleetSource, row: Mapping[str, Any]) -> None:
    """Row rules shared by the extractor and the normalizer (D136); RowError if one fails.

    Keys must be a subset of the requested columns (SODA omits null values, so optional keys may
    be absent); a `placa` key is rejected on its own. Required columns must be present and not
    empty. Every value is a string without control characters."""
    if FORBIDDEN_COLUMN in row:
        raise RowError(FORBIDDEN_COLUMN, "is a forbidden column (personal data is never stored)")
    unexpected = set(row) - source.requested_columns
    if unexpected:
        raise RowError(None, f"has unexpected keys (count={len(unexpected)})")
    missing = source.required - set(row)
    if missing:
        raise RowError(None, f"is missing required keys {sorted(missing)}")
    for name, value in row.items():
        if not isinstance(value, str):
            raise RowError(name, "must be a string")
        if CONTROL_RE.search(value):
            raise RowError(name, "contains a control character")
    for name in source.required:
        if row[name].strip() == "":
            raise RowError(name, "is empty")

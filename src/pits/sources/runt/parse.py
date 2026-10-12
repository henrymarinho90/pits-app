"""Strict parsing of raw RUNT fleet pages into compact records (D97, D98).

Pure functions: no I/O, no clock. Errors name the payload key and row index, never dump data.
Rules are the ones the extractor enforced when it stored the page (contract.py): exact keys,
string values, cantidad an integer >= 1, fecha_de_registro a 4-digit year <= the publication
year, one publication per batch. On top of that, text values must be usable as-is (D98): no
empty value, no leading/trailing whitespace, no CR/LF.

Memory (D98): a record is a flat tuple; repeated strings are interned and the source reference
is rebuilt at serialization from (payload index, row index) instead of being stored.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from pits.sources.runt.contract import EXPECTED_COLUMNS, MONTH_COLUMN, MONTHS, YEAR_COLUMN

_INT_RE = re.compile(r"[0-9]+")
_YEAR_RE = re.compile(r"[0-9]{4}")

# Record layout: the first PK_FIELDS items are the primary key (sort order of the artifact).
#   0 publication_year, 1 publication_month, 2 department_name, 3 municipality_name,
#   4 service_name, 5 vehicle_status, 6 vehicle_class, 7 registration_year,
#   8 vehicle_count, 9 payload index, 10 row index within the payload.
Record = tuple[int, int, str, str, str, str, str, int, int, int, int]
PK_FIELDS = 8
COUNT_INDEX = 8


class RuntDataError(ValueError):
    """Raw RUNT data violates the contract (permanent: retrying cannot fix it)."""


def _text(value: str, where: str) -> str:
    if value == "":
        raise RuntDataError(f"{where} is empty")
    if value != value.strip():
        raise RuntDataError(f"{where} has leading or trailing whitespace")
    if "\r" in value or "\n" in value:
        raise RuntDataError(f"{where} contains a line break")
    return sys.intern(value)


def parse_page(
    rows: Sequence[Mapping[str, Any]],
    *,
    page_key: str,
    page_index: int,
    publication: tuple[int, int],
) -> list[Record]:
    """Validate one page of a batch whose publication is `publication` (year, month)."""
    records: list[Record] = []
    for i, row in enumerate(rows):
        ref = f"{page_key}#row={i}"
        if set(row) != EXPECTED_COLUMNS:
            raise RuntDataError(
                f"{ref} has wrong keys (missing={sorted(EXPECTED_COLUMNS - set(row))}, "
                f"unexpected_count={len(set(row) - EXPECTED_COLUMNS)})"
            )
        for name, value in row.items():
            if not isinstance(value, str):
                raise RuntDataError(f"{ref}.{name} must be a string")
        year_text, month_text = row[YEAR_COLUMN], row[MONTH_COLUMN]
        if not _YEAR_RE.fullmatch(year_text) or month_text not in MONTHS:
            raise RuntDataError(f"{ref} has an invalid publication (year or month)")
        pub_year, pub_month = int(year_text), MONTHS[month_text]
        if (pub_year, pub_month) != publication:
            raise RuntDataError(
                f"{ref} belongs to publication {pub_year:04d}-{pub_month:02d}, "
                f"not {publication[0]:04d}-{publication[1]:02d}"
            )
        count_text = row["cantidad"]
        if not _INT_RE.fullmatch(count_text) or int(count_text) < 1:
            raise RuntDataError(f"{ref}.cantidad is not an integer >= 1")
        registration = row["fecha_de_registro"]
        if not _YEAR_RE.fullmatch(registration) or int(registration) > pub_year:
            raise RuntDataError(
                f"{ref}.fecha_de_registro is not a 4-digit year <= the publication year"
            )
        records.append(
            (
                publication[0],
                publication[1],
                _text(row["nombre_departamento"], f"{ref}.nombre_departamento"),
                _text(row["nombre_municipio"], f"{ref}.nombre_municipio"),
                _text(row["nombre_servicio"], f"{ref}.nombre_servicio"),
                _text(row["estado_del_vehiculo"], f"{ref}.estado_del_vehiculo"),
                _text(row["nombre_de_la_clase"], f"{ref}.nombre_de_la_clase"),
                int(registration),
                int(count_text),
                page_index,
                i,
            )
        )
    return records


def sort_and_check_unique(records: list[Record], payload_keys: Sequence[str]) -> None:
    """Sort in place by the primary key (code point order, no locale); duplicate PK = error."""
    records.sort()
    for previous, current in zip(records, records[1:], strict=False):
        if previous[:PK_FIELDS] == current[:PK_FIELDS]:
            raise RuntDataError(
                "duplicate primary key: "
                f"{source_reference(previous, payload_keys)} and "
                f"{source_reference(current, payload_keys)}"
            )


def source_reference(record: Record, payload_keys: Sequence[str]) -> str:
    return f"{payload_keys[record[9]]}#row={record[10]}"

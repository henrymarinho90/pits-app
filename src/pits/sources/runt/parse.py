"""Strict parsing of raw RUNT fleet pages into compact records (D97, D98).

Pure functions: no I/O, no clock. Errors name the payload key and row index, never dump data.
Row rules are the ones the extractor enforces when it stores the page: one shared
contract.validate_row (exact keys, string values without control characters, cantidad an integer
>= 1, fecha_de_registro a 4-digit year in [1900, publication year], one publication per batch;
D103). On top of that, text values must be usable as-is (D98): no empty value, no
leading/trailing whitespace, no CR/LF.

Memory (D98): a record is a flat tuple; repeated strings are interned and the source reference
is rebuilt at serialization from (payload index, row index) instead of being stored.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from typing import Any

from pits.sources.runt.contract import RowError, validate_row

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
        try:
            validate_row(row, publication)
        except RowError as exc:
            raise RuntDataError(exc.at(ref)) from None
        registration, count_text = row["fecha_de_registro"], row["cantidad"]
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

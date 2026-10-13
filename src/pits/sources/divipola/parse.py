"""Strict parsing of raw DIVIPOLA pages into compact records (D123).

Pure functions: no I/O, no clock. Errors name the payload key and row index, never dump data.
Row rules are the ones the extractor enforces when it stores the page (contract.validate_row).
On top of that, the whole snapshot must be consistent: cod_mpio unique, (cod_dpto, nom_mpio)
unique (the name is the join key of the RUNT mapping once normalized, so a repeated name inside a
department would fan out), and one department name per department code.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from typing import Any

from pits.sources.divipola.contract import RowError, validate_row

# Record layout, in the order of the normalized CSV (the source columns, renamed):
#   0 department_code, 1 department_name, 2 municipality_code, 3 municipality_name,
#   4 municipality_type, 5 longitude, 6 latitude, 7 payload index, 8 row index within the payload.
Record = tuple[str, str, str, str, str, str, str, int, int]
DEPARTMENT_CODE, DEPARTMENT_NAME, MUNICIPALITY_CODE, MUNICIPALITY_NAME = 0, 1, 2, 3


class DivipolaDataError(ValueError):
    """Raw DIVIPOLA data violates the contract (permanent: retrying cannot fix it)."""


def parse_page(
    rows: Sequence[Mapping[str, Any]], *, page_key: str, page_index: int
) -> list[Record]:
    records: list[Record] = []
    for i, row in enumerate(rows):
        try:
            validate_row(row)
        except RowError as exc:
            raise DivipolaDataError(exc.at(f"{page_key}#row={i}")) from None
        records.append(
            (
                sys.intern(row["cod_dpto"]),
                sys.intern(row["dpto"]),
                row["cod_mpio"],
                row["nom_mpio"],
                sys.intern(row["tipo_municipio"]),
                row["longitud"],
                row["latitud"],
                page_index,
                i,
            )
        )
    return records


def source_reference(record: Record, payload_keys: Sequence[str]) -> str:
    return f"{payload_keys[record[7]]}#row={record[8]}"


def sort_and_check_unique(records: list[Record], payload_keys: Sequence[str]) -> None:
    """Sort in place by municipality code (digits only, no locale); inconsistent data = error."""
    records.sort(key=lambda r: r[MUNICIPALITY_CODE])
    names_by_department: dict[str, str] = {}
    seen_names: dict[tuple[str, str], Record] = {}
    previous: Record | None = None
    for record in records:
        if previous is not None and previous[MUNICIPALITY_CODE] == record[MUNICIPALITY_CODE]:
            raise DivipolaDataError(
                "duplicate cod_mpio: "
                f"{source_reference(previous, payload_keys)} and "
                f"{source_reference(record, payload_keys)}"
            )
        previous = record
        department = record[DEPARTMENT_CODE]
        if (
            names_by_department.setdefault(department, record[DEPARTMENT_NAME])
            != record[DEPARTMENT_NAME]
        ):
            raise DivipolaDataError(
                f"department code {department} has more than one name "
                f"({source_reference(record, payload_keys)})"
            )
        key = (department, record[MUNICIPALITY_NAME])
        first = seen_names.setdefault(key, record)
        if first is not record:
            raise DivipolaDataError(
                "duplicate (cod_dpto, nom_mpio): "
                f"{source_reference(first, payload_keys)} and "
                f"{source_reference(record, payload_keys)}"
            )

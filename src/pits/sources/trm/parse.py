"""Strict parsing of raw TRM pages into typed records (D76 d, D77).

Pure functions: no I/O, no clock. Errors name the page key and row index, never dump payloads.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from pits.sources.trm.contract import DATE_RE, EXPECTED_COLUMNS

# Real SODA format of `valor`: plain digits with an optional fraction (no sign, exponent,
# spaces or underscores). NaN/Infinity/"4E+3"/"1_000" would otherwise be accepted by Decimal().
_VALOR_RE = re.compile(r"\d+(\.\d+)?")
EXPECTED_UNIT = "COP"  # D77: valor is COP per 1 USD


class TrmDataError(ValueError):
    """Raw TRM data violates the contract (permanent: retrying cannot fix it)."""


@dataclass(frozen=True)
class TrmRecord:
    """One TRM validity range: `rate` COP per 1 USD for valid_from..valid_to inclusive."""

    valid_from: date
    valid_to: date
    rate: Decimal
    source_reference: str  # '<raw payload key>#row=<index within the page>'


def _parse_date(value: Any, where: str) -> date:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        raise TrmDataError(f"{where} is not a midnight timestamp (YYYY-MM-DDT00:00:00.000)")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise TrmDataError(f"{where} is not a valid date") from exc


def parse_page(rows: Sequence[Mapping[str, Any]], *, page_key: str) -> list[TrmRecord]:
    """Validate one page and return its records; vigenciadesde must be strictly ascending."""
    records: list[TrmRecord] = []
    previous: date | None = None
    for i, row in enumerate(rows):
        ref = f"{page_key}#row={i}"
        if set(row) != EXPECTED_COLUMNS:
            # Only expected names are echoed; unexpected keys are counted, never printed.
            raise TrmDataError(
                f"{ref} has wrong keys (missing={sorted(EXPECTED_COLUMNS - set(row))}, "
                f"unexpected_count={len(set(row) - EXPECTED_COLUMNS)})"
            )
        for name in ("valor", "unidad"):
            if not isinstance(row[name], str):
                raise TrmDataError(f"{ref}.{name} must be a string")
        if row["unidad"] != EXPECTED_UNIT:
            raise TrmDataError(f"{ref}.unidad must be {EXPECTED_UNIT!r} (D77)")
        if not _VALOR_RE.fullmatch(row["valor"]):
            raise TrmDataError(f"{ref}.valor is not a plain non-negative decimal number")
        try:
            rate = Decimal(row["valor"])
        except InvalidOperation:
            raise TrmDataError(f"{ref}.valor is not a decimal number") from None
        if not rate.is_finite():
            raise TrmDataError(f"{ref}.valor is not a finite decimal number")
        if rate <= 0:
            raise TrmDataError(f"{ref}.valor must be greater than zero")
        valid_from = _parse_date(row["vigenciadesde"], f"{ref}.vigenciadesde")
        valid_to = _parse_date(row["vigenciahasta"], f"{ref}.vigenciahasta")
        if valid_to < valid_from:
            raise TrmDataError(f"{ref}.vigenciahasta is before vigenciadesde")
        if previous is not None and valid_from <= previous:
            raise TrmDataError(f"{ref}.vigenciadesde is duplicated or out of order")
        previous = valid_from
        records.append(TrmRecord(valid_from, valid_to, rate, ref))
    return records

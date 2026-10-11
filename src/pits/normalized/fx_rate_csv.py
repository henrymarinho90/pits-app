"""Deterministic fx_rate CSV (D76 e, D77): the only serializer of the normalized artifact.

Format: UTF-8 without BOM, LF, comma separator, no quoting (fields are validated against a
safe charset instead), exact header, one row per rate_date ascending, ISO dates, USD->COP,
rate as a fixed-point Decimal without exponent or trailing zeros and without rounding.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from pits.sources.trm.replay import FxDay

HEADER = "rate_date,currency_from,currency_to,rate,source_reference"
CURRENCY_FROM = "USD"
CURRENCY_TO = "COP"
CONTENT_TYPE = "text/csv"

# Characters seen in raw keys: letters, digits and _ . = # / : - (no comma, quote or newline).
_SAFE_FIELD_RE = re.compile(r"[A-Za-z0-9_.=#/:\-]+")


class FxRateCsvError(ValueError):
    """The daily series cannot be serialized safely (permanent)."""


def format_rate(rate: Decimal) -> str:
    """Fixed-point text without exponent and without trailing zeros: 4000, 635.7, 3194.44."""
    if not rate.is_finite() or rate <= 0:
        raise FxRateCsvError("rate must be a finite decimal greater than zero")
    text = format(rate, "f")  # never an exponent, keeps every digit (no rounding)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def serialize_fx_rate(days: Sequence[FxDay]) -> bytes:
    """Serialize strictly ascending, non-empty daily rates; raises FxRateCsvError otherwise."""
    if not days:
        raise FxRateCsvError("no rows to serialize")
    lines = [HEADER]
    previous: date | None = None
    for day in days:
        if previous is not None and day.rate_date <= previous:
            raise FxRateCsvError(f"rate_date not strictly ascending at {day.rate_date}")
        previous = day.rate_date
        if not _SAFE_FIELD_RE.fullmatch(day.source_reference):
            raise FxRateCsvError(f"source_reference for {day.rate_date} has unsafe characters")
        lines.append(
            ",".join(
                (
                    day.rate_date.isoformat(),
                    CURRENCY_FROM,
                    CURRENCY_TO,
                    format_rate(day.rate),
                    day.source_reference,
                )
            )
        )
    return ("\n".join(lines) + "\n").encode("utf-8")

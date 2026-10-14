"""Deterministic regional_fleet_brand CSV (D137): the only serializer of the artifact.

Format: UTF-8 without BOM, LF, comma separator, exact header, csv QUOTE_MINIMAL, one row per
(vehicle_class, brand, line, service_name, vehicle_status) ordered by those five values (plain
code point order, no locale). Values are exactly as published (no case folding or trimming:
staging normalizes). service_name and vehicle_status are empty for Risaralda, which does not
publish them (the landing loader turns an empty field into NULL). The plate never appears: the
normalizer drops every column except the five keys. One object of at most 8 MiB.
"""

from __future__ import annotations

from collections.abc import Sequence

from pits.ingestion.raw_store import MAX_OBJECT_BYTES
from pits.normalized.divipola_csv import RowWriter

HEADER = "vehicle_class,brand,line,service_name,vehicle_status,vehicle_count,source_reference"
HEADER_BYTES = (HEADER + "\n").encode("utf-8")
CONTENT_TYPE = "text/csv"
CSV_NAME = "brand_count.csv"

# (vehicle_class, brand, line, service_name, vehicle_status, vehicle_count); "" = not published.
Row = tuple[str, str, str, str, str, int]


class BrandFleetCsvError(ValueError):
    """The rows cannot be serialized safely (permanent)."""


def serialize_brand_count(rows: Sequence[Row], source_reference: str) -> bytes:
    """Serialize non-empty rows, already sorted and unique by their five keys (header included)."""
    if not rows:
        raise BrandFleetCsvError("no rows to serialize")
    writer = RowWriter()
    chunks = [HEADER_BYTES]
    previous: tuple[str, ...] | None = None
    for row in rows:
        key = row[:5]
        if row[5] < 1:
            raise BrandFleetCsvError("vehicle_count must be positive")
        if previous is not None and key <= previous:
            raise BrandFleetCsvError("rows must be sorted and unique by their five keys")
        previous = key
        chunks.append(writer.line((*row, source_reference)))
    body = b"".join(chunks)
    if len(body) > MAX_OBJECT_BYTES:
        raise BrandFleetCsvError("the CSV is larger than the single-object limit")
    return body

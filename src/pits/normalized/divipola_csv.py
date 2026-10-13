"""Deterministic divipola_municipality CSV (D123): the only serializer of the artifact.

Format: UTF-8 without BOM, LF, comma separator, exact header, csv QUOTE_MINIMAL (names such as
"BOGOTÁ, D.C." and the decimal-comma coordinates are quoted), one row per municipality ordered
by municipality_code. Values are exactly as published: the decimal comma stays; staging converts
it (same as D100 for text normalization). A single object: the dataset has about 1,100 rows.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence

from pits.ingestion.raw_store import MAX_OBJECT_BYTES
from pits.sources.divipola.parse import Record, source_reference

HEADER = (
    "department_code,department_name,municipality_code,municipality_name,municipality_type,"
    "longitude,latitude,source_reference"
)
HEADER_BYTES = (HEADER + "\n").encode("utf-8")
CONTENT_TYPE = "text/csv"
CSV_NAME = "municipality.csv"


class DivipolaCsvError(ValueError):
    """The rows cannot be serialized safely (permanent)."""


class RowWriter:
    """The only row serializer: one csv.writer reused; `line` returns the encoded CSV line.

    Takes the 8 CSV fields in header order. The serializer of the artifact and the loader's
    digest rebuild both use it, so their bytes cannot diverge.
    """

    def __init__(self) -> None:
        self._buffer = io.StringIO()
        self._writer = csv.writer(self._buffer, lineterminator="\n")

    def line(self, values: Sequence[object]) -> bytes:
        self._buffer.seek(0)
        self._buffer.truncate()
        self._writer.writerow(values)
        return self._buffer.getvalue().encode("utf-8")


def serialize_divipola(records: Sequence[Record], payload_keys: Sequence[str]) -> bytes:
    """Serialize sorted, non-empty records into the CSV (header included)."""
    if not records:
        raise DivipolaCsvError("no rows to serialize")
    writer = RowWriter()
    chunks = [HEADER_BYTES]
    for record in records:
        chunks.append(writer.line((*record[:7], source_reference(record, payload_keys))))
    body = b"".join(chunks)
    if len(body) > MAX_OBJECT_BYTES:
        raise DivipolaCsvError("the CSV is larger than the single-object limit")
    return body

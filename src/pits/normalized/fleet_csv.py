"""Deterministic vehicle_fleet_snapshot CSV parts (D98): the only serializer of the artifact.

Format: UTF-8 without BOM, LF, comma separator, header in every part, values as published
(csv QUOTE_MINIMAL only where a value contains a comma or a quote). Rows arrive already sorted
by the primary key. A part holds at most MAX_PART_ROWS rows and MAX_PART_BYTES bytes (single
put_object, no multipart); a part is closed before the row that would exceed either limit.
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Sequence
from dataclasses import dataclass

from pits.ingestion.raw_store import MAX_OBJECT_BYTES
from pits.sources.runt.parse import Record, source_reference

HEADER = (
    "publication_year,publication_month,department_name,municipality_name,service_name,"
    "vehicle_status,vehicle_class,registration_year,vehicle_count,source_reference"
)
CONTENT_TYPE = "text/csv"
MAX_PART_ROWS = 20_000
MAX_PART_BYTES = MAX_OBJECT_BYTES
HEADER_BYTES = (HEADER + "\n").encode("utf-8")


class FleetCsvError(ValueError):
    """The rows cannot be serialized safely (permanent)."""


@dataclass(frozen=True)
class FleetPart:
    body: bytes
    row_count: int

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


def part_name(index: int) -> str:
    return f"part-{index:05d}.csv"


class RowWriter:
    """The only row serializer: one csv.writer reused; `line` returns the encoded CSV line.

    Takes the 10 CSV fields in header order (QUOTE_MINIMAL, LF, UTF-8). The serializer of the
    artifact and the loader's digest rebuild both use it, so their bytes cannot diverge.
    """

    def __init__(self) -> None:
        self._buffer = io.StringIO()
        self._writer = csv.writer(self._buffer, lineterminator="\n")

    def line(self, values: Sequence[object]) -> bytes:
        self._buffer.seek(0)
        self._buffer.truncate()
        self._writer.writerow(values)
        return self._buffer.getvalue().encode("utf-8")


class _LineWriter:
    """Record -> encoded line, building the source reference from (payload, row index)."""

    def __init__(self, payload_keys: Sequence[str]) -> None:
        self._payload_keys = payload_keys
        self._rows = RowWriter()

    def line(self, record: Record) -> bytes:
        return self._rows.line((*record[:9], source_reference(record, self._payload_keys)))


def serialize_fleet(
    records: Sequence[Record],
    payload_keys: Sequence[str],
    *,
    max_rows: int = MAX_PART_ROWS,
) -> list[FleetPart]:
    """Serialize sorted, non-empty records into parts (each with the header)."""
    if not records:
        raise FleetCsvError("no rows to serialize")
    writer = _LineWriter(payload_keys)
    parts: list[FleetPart] = []
    chunks: list[bytes] = [HEADER_BYTES]
    size = len(HEADER_BYTES)
    rows = 0
    for record in records:
        line = writer.line(record)
        if len(HEADER_BYTES) + len(line) > MAX_PART_BYTES:
            raise FleetCsvError("a single row is larger than the part size limit")
        if rows and (rows >= max_rows or size + len(line) > MAX_PART_BYTES):
            parts.append(FleetPart(b"".join(chunks), rows))
            chunks, size, rows = [HEADER_BYTES], len(HEADER_BYTES), 0
        chunks.append(line)
        size += len(line)
        rows += 1
    parts.append(FleetPart(b"".join(chunks), rows))
    return parts


def logical_content(parts: Sequence[FleetPart]) -> tuple[str, int]:
    """(sha256, size) of the logical CSV: the header once, then every row of every part."""
    digest = hashlib.sha256(HEADER_BYTES)
    size = len(HEADER_BYTES)
    for part in parts:
        digest.update(memoryview(part.body)[len(HEADER_BYTES) :])
        size += len(part.body) - len(HEADER_BYTES)
    return digest.hexdigest(), size

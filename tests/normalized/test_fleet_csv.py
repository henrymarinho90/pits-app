"""Pure tests for pits.normalized.fleet_csv (deterministic CSV parts)."""

from __future__ import annotations

import csv
import hashlib
import io

import pytest
from runt_support import raw_row

from pits.normalized import fleet_csv
from pits.normalized.fleet_csv import (
    HEADER,
    FleetCsvError,
    logical_content,
    serialize_fleet,
)
from pits.sources.runt.parse import parse_page, sort_and_check_unique

KEYS = ["raw/payload-00000.json"]


def records(rows):
    recs = parse_page(rows, page_key=KEYS[0], page_index=0, publication=(2026, 10))
    sort_and_check_unique(recs, KEYS)
    return recs


def test_header_is_the_d98_header():
    assert HEADER == (
        "publication_year,publication_month,department_name,municipality_name,service_name,"
        "vehicle_status,vehicle_class,registration_year,vehicle_count,source_reference"
    )


def test_single_part_layout_lf_no_bom_and_source_reference():
    (part,) = serialize_fleet(records([raw_row(1, nombre_municipio="CALI"), raw_row(0)]), KEYS)
    lines = part.body.decode("utf-8").split("\n")
    assert part.body[:3] != b"\xef\xbb\xbf" and b"\r" not in part.body
    assert lines[0] == HEADER and lines[-1] == ""
    assert lines[1] == (
        "2026,10,ANTIOQUIA,CALI,PARTICULAR,ACTIVO,CAMPERO,1999,3,raw/payload-00000.json#row=0"
    )
    assert lines[2].startswith("2026,10,ANTIOQUIA,MUNI000000,")
    assert part.row_count == 2 and part.sha256 == hashlib.sha256(part.body).hexdigest()


def test_values_are_written_as_is_with_accents_and_quoted_only_when_needed():
    rows = [
        raw_row(0, nombre_municipio="AÑASCO"),
        raw_row(1, nombre_departamento="ARCHIPIELAGO DE SAN ANDRES, PROVIDENCIA"),
        raw_row(2, nombre_de_la_clase='MAQ "X"'),
    ]
    text = serialize_fleet(records(rows), KEYS)[0].body.decode("utf-8")
    assert "AÑASCO" in text
    assert '"ARCHIPIELAGO DE SAN ANDRES, PROVIDENCIA"' in text
    assert '"MAQ ""X"""' in text
    assert "ANTIOQUIA,AÑASCO,PARTICULAR" in text  # plain values stay unquoted


def test_parts_split_by_row_count_each_with_header():
    parts = serialize_fleet(records([raw_row(i) for i in range(7)]), KEYS, max_rows=3)
    assert [p.row_count for p in parts] == [3, 3, 1]
    assert all(p.body.startswith((HEADER + "\n").encode()) for p in parts)
    assert all(p.body.count(b"\n") == p.row_count + 1 for p in parts)


def test_parts_split_by_byte_limit(monkeypatch):
    one = len(serialize_fleet(records([raw_row(0)]), KEYS)[0].body)
    monkeypatch.setattr(fleet_csv, "MAX_PART_BYTES", one + 1)  # header + one row only
    parts = serialize_fleet(records([raw_row(i) for i in range(3)]), KEYS)
    assert [p.row_count for p in parts] == [1, 1, 1]
    assert all(len(p.body) <= one + 1 for p in parts)


def test_single_row_above_the_limit_is_an_error(monkeypatch):
    monkeypatch.setattr(fleet_csv, "MAX_PART_BYTES", len(fleet_csv.HEADER_BYTES) + 5)
    with pytest.raises(FleetCsvError, match="larger than the part size limit"):
        serialize_fleet(records([raw_row(0)]), KEYS)


def test_empty_input_is_an_error():
    with pytest.raises(FleetCsvError, match="no rows"):
        serialize_fleet([], KEYS)


def test_logical_content_is_header_once_then_every_row():
    parts = serialize_fleet(records([raw_row(i) for i in range(7)]), KEYS, max_rows=3)
    sha, size = logical_content(parts)
    logical = (HEADER + "\n").encode() + b"".join(
        p.body[len((HEADER + "\n").encode()) :] for p in parts
    )
    assert (sha, size) == (hashlib.sha256(logical).hexdigest(), len(logical))
    assert logical.count(b"\n") == 8
    # Reproducible, and independent of the split.
    single = serialize_fleet(records([raw_row(i) for i in range(7)]), KEYS)
    assert logical_content(single) == (sha, size)


def test_serialization_is_deterministic():
    rows = [raw_row(i) for i in range(5)]
    first = serialize_fleet(records(rows), KEYS, max_rows=2)
    second = serialize_fleet(records(rows), KEYS, max_rows=2)
    assert [p.body for p in first] == [p.body for p in second]


def test_csv_roundtrip_with_commas_and_quotes_is_byte_identical():
    rows = [
        raw_row(0, nombre_departamento="ARCHIPIELAGO DE SAN ANDRES, PROVIDENCIA"),
        raw_row(1, nombre_de_la_clase='MAQ "X", PESADA'),
        raw_row(2, nombre_municipio='A"B'),
        raw_row(3, nombre_municipio="AÑASCO"),
    ]
    for part in serialize_fleet(records(rows), KEYS, max_rows=3):
        parsed = list(csv.reader(io.StringIO(part.body.decode("utf-8"), newline="")))
        assert parsed[0] == HEADER.split(",") and all(len(r) == 10 for r in parsed)
        out = io.StringIO()
        csv.writer(out, lineterminator="\n").writerows(parsed)
        assert out.getvalue().encode("utf-8") == part.body

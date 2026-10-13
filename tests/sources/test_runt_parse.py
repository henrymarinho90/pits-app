"""Pure tests for pits.sources.runt.parse (strict rows -> compact records)."""

from __future__ import annotations

import sys

import pytest
from runt_support import raw_row

from pits.sources.runt.parse import (
    RuntDataError,
    parse_page,
    sort_and_check_unique,
    source_reference,
)

PUB = (2026, 10)


def parse(rows, key="k/payload-00000.json", index=0, publication=PUB):
    return parse_page(rows, page_key=key, page_index=index, publication=publication)


def test_valid_row_becomes_flat_tuple_with_numeric_month_and_position():
    (record,) = parse([raw_row(0, nombre_municipio="CALI", cantidad="7", fecha_de_registro="2001")])
    assert record == (
        2026,
        10,
        "ANTIOQUIA",
        "CALI",
        "PARTICULAR",
        "ACTIVO",
        "CAMPERO",
        2001,
        7,
        0,
        0,
    )
    assert source_reference(record, ["k/payload-00000.json"]) == "k/payload-00000.json#row=0"


def test_month_label_is_converted_to_its_number():
    (record,) = parse([raw_row(0, year=2025, month=1)], publication=(2025, 1))
    assert record[:2] == (2025, 1)


def test_repeated_strings_are_interned():
    first, second = parse([raw_row(0), raw_row(1)])
    # Equal strings parsed separately are the very same object.
    assert first[2] is second[2] is sys.intern("ANTIOQUIA")


@pytest.mark.parametrize(
    "bad",
    [
        {"nombre_municipio": ""},
        {"nombre_municipio": " CALI"},
        {"nombre_municipio": "CALI "},
        {"nombre_servicio": "\tX"},
        {"nombre_de_la_clase": "A\nB"},
        {"nombre_departamento": "A\rB"},
        {"nombre_municipio": "CA\x00LI"},  # D103: NUL and any Cc inside a value
        {"nombre_municipio": "CA\x1fLI"},
        {"nombre_municipio": "CA\x7fLI"},
        {"nombre_municipio": "CA\x85LI"},  # C1 control (NEL)
        {"fecha_de_registro": "1899"},  # D103: below the landing CHECK
        {"fecha_de_registro": "0000"},
        {"cantidad": "0"},
        {"cantidad": "-1"},
        {"cantidad": "1.5"},
        {"cantidad": ""},
        {"fecha_de_registro": "2027"},
        {"fecha_de_registro": "99"},
        {"mes_de_publicacion": "NOVIEMBRE"},
        {"mes_de_publicacion": "octubre"},
        {"a_o_de_publicacion": "2025"},
        {"a_o_de_publicacion": "26"},
    ],
)
def test_invalid_row_is_rejected(bad):
    with pytest.raises(RuntDataError, match="payload-00000.json#row=0"):
        parse([raw_row(0, **bad)])


@pytest.mark.parametrize("year", ["1900", "1901"])
def test_registration_years_1900_and_1901_are_kept_as_is(year):
    (record,) = parse([raw_row(0, fecha_de_registro=year)])
    assert record[7] == int(year)


def test_non_cc_unicode_is_kept():
    # Format/space/other characters are not control characters (category Cc).
    (record,) = parse([raw_row(0, nombre_municipio="A\u200bB\u00a0C\u00d1")])
    assert record[3] == "A\u200bB\u00a0C\u00d1"


def test_wrong_keys_and_non_string_values_are_rejected():
    row = raw_row(0)
    del row["cantidad"]
    with pytest.raises(RuntDataError, match="wrong keys"):
        parse([row])
    with pytest.raises(RuntDataError, match="wrong keys"):
        parse([{**raw_row(0), "extra": "x"}])
    with pytest.raises(RuntDataError, match="must be a string"):
        parse([{**raw_row(0), "cantidad": 3}])


def test_error_names_the_row_and_never_echoes_values():
    with pytest.raises(RuntDataError) as exc_info:
        parse([raw_row(0), raw_row(1, nombre_municipio=" SECRETO")])
    assert "#row=1" in str(exc_info.value) and "SECRETO" not in str(exc_info.value)


def test_sort_is_by_primary_key_in_code_point_order():
    rows = [
        raw_row(0, nombre_municipio="ÑA"),  # N with tilde sorts after every ASCII letter
        raw_row(1, nombre_municipio="Z"),
        raw_row(2, nombre_municipio="a"),  # lowercase after uppercase: no locale, no casefold
        raw_row(3, nombre_municipio="B"),
        raw_row(4, nombre_municipio="B", fecha_de_registro="1990"),
    ]
    records = parse(rows)
    sort_and_check_unique(records, ["k"])
    assert [(r[3], r[7]) for r in records] == [
        ("B", 1990),
        ("B", 1999),
        ("Z", 1999),
        ("a", 1999),
        ("ÑA", 1999),
    ]


def test_duplicate_primary_key_is_an_error_naming_both_rows():
    # Same PK, different cantidad: still a duplicate.
    records = parse([raw_row(0), raw_row(1, nombre_municipio="OTRO"), raw_row(0, cantidad="9")])
    with pytest.raises(RuntDataError, match=r"duplicate primary key: k#row=0 and k#row=2"):
        sort_and_check_unique(records, ["k"])

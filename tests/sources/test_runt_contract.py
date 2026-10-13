"""Pure tests for contract.validate_row and RowError (D103)."""

from __future__ import annotations

import unicodedata

import pytest
from runt_support import raw_row

from pits.sources.runt.contract import CONTROL_RE, RowError, validate_row

PUB = (2026, 10)


def test_control_regex_is_exactly_unicode_category_cc():
    cc = {cp for cp in range(0x110000) if unicodedata.category(chr(cp)) == "Cc"}
    matched = {cp for cp in range(0x110000) if CONTROL_RE.search(chr(cp))}
    assert matched == cc and len(cc) == 65


def test_valid_row_passes():
    validate_row(raw_row(0), PUB)


@pytest.mark.parametrize("year", ["1900", "1901", "2026"])
def test_registration_year_edges_are_valid(year):
    validate_row(raw_row(0, fecha_de_registro=year), PUB)


@pytest.mark.parametrize("year", ["1899", "0000", "2027", "99", "abcd"])
def test_registration_year_outside_range_is_rejected(year):
    with pytest.raises(RowError) as exc:
        validate_row(raw_row(0, fecha_de_registro=year), PUB)
    assert exc.value.field == "fecha_de_registro"


@pytest.mark.parametrize("char", [chr(0), chr(0x1F), chr(0x7F), chr(0x85), chr(0x9F)])
def test_control_character_is_rejected_without_leaking_the_value(char):
    value = f"CA{char}LI"
    with pytest.raises(RowError) as exc:
        validate_row(raw_row(0, nombre_municipio=value), PUB)
    error = exc.value
    assert error.field == "nombre_municipio" and "control character" in error.problem
    for text in (str(error), error.at("page#row=3")):
        assert value not in text and "CA" not in text and "LI" not in text
    assert error.at("page#row=3").startswith("page#row=3.nombre_municipio ")


def test_row_level_error_has_no_field_and_at_prefixes_the_reference():
    row = raw_row(0, year=2025)
    with pytest.raises(RowError) as exc:
        validate_row(row, PUB)
    assert exc.value.field is None
    assert exc.value.at("r") == f"r {exc.value.problem}"
    assert "2026-10" in exc.value.problem


def test_wrong_keys_never_echo_extra_names_or_values():
    with pytest.raises(RowError) as exc:
        validate_row({**raw_row(0), "secret_extra": "SECRETO"}, PUB)
    assert "SECRETO" not in str(exc.value) and "secret_extra" not in str(exc.value)

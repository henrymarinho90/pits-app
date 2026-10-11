"""Pure tests for pits.sources.trm.parse."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from pits.sources.trm.parse import TrmDataError, TrmRecord, parse_page

KEY = "superfinanciera_trm/extraction_date=2026-10-10/batch_id=b/payload-00000.json"


def row(frm="2026-10-10", to="2026-10-13", valor="3194.44", unidad="COP"):
    return {
        "valor": valor,
        "unidad": unidad,
        "vigenciadesde": f"{frm}T00:00:00.000",
        "vigenciahasta": f"{to}T00:00:00.000",
    }


def test_parses_records_with_decimal_and_source_reference():
    records = parse_page([row(), row("2026-10-14", "2026-10-14", "3200")], page_key=KEY)
    assert records == [
        TrmRecord(date(2026, 10, 10), date(2026, 10, 13), Decimal("3194.44"), f"{KEY}#row=0"),
        TrmRecord(date(2026, 10, 14), date(2026, 10, 14), Decimal("3200"), f"{KEY}#row=1"),
    ]
    assert isinstance(records[0].rate, Decimal)


def test_empty_page_is_empty_list():
    assert parse_page([], page_key=KEY) == []


@pytest.mark.parametrize(
    ("bad", "match"),
    [
        (row(valor="NaN"), "plain"),
        (row(valor="Infinity"), "plain"),
        (row(valor="-Infinity"), "plain"),
        (row(valor="1_000"), "plain"),
        (row(valor=" 4000 "), "plain"),
        (row(valor="4E+3"), "plain"),
        (row(valor="+4000.50"), "plain"),
        (row(valor="4000."), "plain"),
        (row(valor=""), "plain"),
        (row(valor="0"), "greater than zero"),
        (row(valor="-1.5"), "plain"),
        (row(valor="0.00"), "greater than zero"),
        (row(valor="abc"), "plain"),
        (row(unidad="USD"), "unidad"),
        (row(frm="2026-02-30"), "valid date"),
        (row(to="2026-13-01"), "valid date"),
        (row(to="2026-10-09"), "before"),
        ({**row(), "extra": "x"}, "wrong keys"),
        ({k: v for k, v in row().items() if k != "valor"}, "wrong keys"),
        ({**row(), "valor": 3194.44}, "must be a string"),
        ({**row(), "vigenciadesde": "2026-10-10"}, "midnight"),
        ({**row(), "vigenciadesde": "2026-10-10T01:00:00.000"}, "midnight"),
        ({**row(), "vigenciahasta": None}, "midnight"),
    ],
)
def test_invalid_row_is_rejected_with_key_and_row_index(bad, match):
    with pytest.raises(TrmDataError, match=match) as err:
        parse_page([row("2026-10-01", "2026-10-02"), bad], page_key=KEY)
    assert f"{KEY}#row=1" in str(err.value)
    assert "3194" not in str(err.value)  # no payload values dumped


def test_duplicate_or_unordered_vigenciadesde_rejected():
    with pytest.raises(TrmDataError, match="out of order"):
        parse_page([row("2026-10-10"), row("2026-10-10")], page_key=KEY)
    with pytest.raises(TrmDataError, match="out of order"):
        parse_page([row("2026-10-11"), row("2026-10-10")], page_key=KEY)


def test_wrong_keys_error_does_not_echo_unexpected_key_names():
    hostile = {**row(), "SECRET-KEY-" + "x" * 50: "v"}
    with pytest.raises(TrmDataError, match="unexpected_count=1") as err:
        parse_page([hostile], page_key=KEY)
    assert "SECRET-KEY" not in str(err.value)

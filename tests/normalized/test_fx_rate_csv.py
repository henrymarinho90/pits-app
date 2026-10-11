"""Pure tests for pits.normalized.fx_rate_csv."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from pits.normalized.fx_rate_csv import FxRateCsvError, format_rate, serialize_fx_rate
from pits.sources.trm.replay import FxDay

REF = "superfinanciera_trm/extraction_date=2026-10-10/batch_id=b/payload-00000.json#row=7"


def day(d, rate="3194.44", ref=REF):
    return FxDay(d, Decimal(rate), ref)


def test_exact_bytes_for_a_four_day_range():
    start = date(2026, 10, 10)
    data = serialize_fx_rate([day(start + timedelta(days=i)) for i in range(4)])
    expected = (
        "rate_date,currency_from,currency_to,rate,source_reference\n"
        f"2026-10-10,USD,COP,3194.44,{REF}\n"
        f"2026-10-11,USD,COP,3194.44,{REF}\n"
        f"2026-10-12,USD,COP,3194.44,{REF}\n"
        f"2026-10-13,USD,COP,3194.44,{REF}\n"
    ).encode()
    assert data == expected
    assert not data.startswith(b"\xef\xbb\xbf") and b"\r" not in data and b'"' not in data


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("635.7", "635.7"),
        ("635.70", "635.7"),
        ("4000", "4000"),
        ("4000.00", "4000"),
        ("4E+3", "4000"),
        ("0.000123", "0.000123"),
        ("3194.440000000001", "3194.440000000001"),  # no rounding
        ("100", "100"),
        ("1E+2", "100"),
        ("12345678901234567890.5", "12345678901234567890.5"),
    ],
)
def test_format_rate_is_fixed_point_without_trailing_zeros(text, expected):
    assert format_rate(Decimal(text)) == expected


@pytest.mark.parametrize("bad", ["0", "-1", "NaN", "Infinity"])
def test_format_rate_rejects_non_positive_or_non_finite(bad):
    with pytest.raises(FxRateCsvError):
        format_rate(Decimal(bad))


def test_integer_and_decimal_rows():
    data = serialize_fx_rate(
        [day(date(2026, 1, 1), "4000.00", "a#row=0"), day(date(2026, 1, 2), "635.7", "a#row=1")]
    )
    lines = data.decode().split("\n")
    assert lines[1] == "2026-01-01,USD,COP,4000,a#row=0"
    assert lines[2] == "2026-01-02,USD,COP,635.7,a#row=1"
    assert lines[3] == ""  # ends with a single LF


@pytest.mark.parametrize("ref", ["a,b", 'a"b', "a\nb", "a\rb", "a b", "ñ#row=0", "", "a;b"])
def test_unsafe_source_reference_is_rejected(ref):
    with pytest.raises(FxRateCsvError, match="unsafe"):
        serialize_fx_rate([day(date(2026, 1, 1), ref=ref)])


def test_empty_and_unsorted_input_rejected():
    with pytest.raises(FxRateCsvError, match="no rows"):
        serialize_fx_rate([])
    with pytest.raises(FxRateCsvError, match="ascending"):
        serialize_fx_rate([day(date(2026, 1, 2)), day(date(2026, 1, 1))])
    with pytest.raises(FxRateCsvError, match="ascending"):
        serialize_fx_rate([day(date(2026, 1, 1)), day(date(2026, 1, 1))])

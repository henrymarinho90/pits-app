"""Offline checks of the Hamilton reference model (D143, D144 a); no database, no dbt.

tests/pg is on pythonpath (pyproject), so the model is imported from brand_synthetic_support.
"""

from __future__ import annotations

import random
from decimal import Decimal

import pytest
from brand_synthetic_support import (
    UNCALIBRATED,
    allocate_brands,
    allocate_lines,
    build_cells,
    hamilton,
    quota,
)

D = Decimal


def counts(result):
    return {k: v[0] for k, v in result.items()}


def test_conservation_and_bound_on_irregular_shares():
    shares = {"A": D(1) / 3, "B": D(1) / 3, "C": D(1) / 3}
    shares = {k: v.quantize(D("1e-20")) for k, v in shares.items()}
    shares["C"] = D(1) - shares["A"] - shares["B"]
    for n in (1, 2, 3, 4, 10, 1000, 99999):
        result = hamilton(n, shares)
        assert sum(counts(result).values()) == n
        for count, q in result.values():
            assert abs(count - q) < 1


def test_alphabetical_tie_break_by_code_point():
    # two equal quotas of 1.5 and one remainder to give: the smaller key wins
    assert counts(hamilton(3, {"ZETA": D("0.5"), "ALFA": D("0.5")})) == {"ALFA": 2, "ZETA": 1}
    # code point order, not locale: upper case before lower case, digits before letters
    assert counts(hamilton(1, {"b": D("0.5"), "B": D("0.5")})) == {"B": 1}
    assert counts(hamilton(1, {"A": D("0.5"), "1": D("0.5")})) == {"1": 1}


def test_larger_remainder_wins_before_the_alphabet():
    # quotas 2.7 and 1.3 for N = 4: floors 2 + 1, R = 1 goes to the .7 although "Z" > "A"
    assert counts(hamilton(4, {"A": D("0.325"), "Z": D("0.675")})) == {"A": 1, "Z": 3}


def test_equal_remainder_goes_to_the_larger_quota():
    # N = 2, shares .75/.25: quotas 1.5 and 0.5, equal remainders .5, so the larger quota wins
    assert counts(hamilton(2, {"A": D("0.75"), "B": D("0.25")})) == {"A": 2}


def test_n_equal_one_gives_the_single_unit_to_the_top_quota():
    assert counts(hamilton(1, {"A": D("0.2"), "B": D("0.5"), "C": D("0.3")})) == {"B": 1}


def test_n_equal_zero_gives_no_rows():
    assert hamilton(0, {"A": D("0.5"), "B": D("0.5")}) == {}


def test_negative_total_is_an_error():
    with pytest.raises(ValueError):
        hamilton(-1, {"A": D(1)})


def test_exact_quotas_are_kept_and_zero_counts_dropped():
    result = hamilton(100, {"A": D("0.5"), "B": D("0.3"), "C": D("0.2"), "D": D(0)})
    assert counts(result) == {"A": 50, "B": 30, "C": 20}
    assert all(q == q.to_integral_value() for _, q in result.values())


def test_quota_is_quantized_to_12_decimals_half_up():
    assert quota(1, D("0.0000000000005")) == D("0.000000000001")  # 5e-13 rounds up
    assert quota(1, D("0.0000000000004")) == D("0")
    assert quota(3, D("0.3333333333333333")) == D("1.000000000000")


def test_input_order_does_not_change_the_result():
    shares = {f"B{i:02d}": D(i) / D(231) for i in range(1, 22)}  # sums to 1
    assert abs(sum(shares.values()) - D(1)) < D("1e-20")
    reference = hamilton(1234, shares)
    items = list(shares.items())
    rng = random.Random(7)
    for _ in range(10):
        rng.shuffle(items)
        assert hamilton(1234, dict(items)) == reference


def test_cells_use_the_latest_publication_and_the_particular_segment():
    rows = [
        (2026, 9, "D", "M", "AUTOMOVIL", "01", "01001", "car", "particular", 99999),
        (2026, 10, "D", "M", "AUTOMOVIL", "01", "01001", "car", "particular", 2000),
        (2026, 10, "D", "M", "AUTOMOVIL", "01", "01001", "car", "particular", 1000),
        (2026, 10, "D", "M", "AUTOMOVIL", "01", "01001", "car", "fleet", 500),
    ]
    assert build_cells(rows) == {(2026, 10, "D", "M", "AUTOMOVIL"): ("01", "01001", "car", 3000)}
    assert build_cells([]) == {}


def test_uncalibrated_class_carries_the_whole_n_in_both_stages():
    cells = {(2026, 10, "D", "M", "GRUA"): ("01", "01001", "machinery", 7)}
    brands = allocate_brands(cells, {"AUTOMOVIL": {"A": D(1)}})
    assert brands == {(2026, 10, "D", "M", "GRUA", UNCALIBRATED): (7, D(7))}
    lines = allocate_lines(brands, cells, {})
    assert lines == {(2026, 10, "D", "01", "GRUA", UNCALIBRATED, UNCALIBRATED): (7, D(7))}


def test_line_stage_sums_the_municipalities_of_the_department_first():
    cells = {
        (2026, 10, "D", "M1", "AUTOMOVIL"): ("01", "01001", "car", 1),
        (2026, 10, "D", "M2", "AUTOMOVIL"): ("01", "01002", "car", 1),
    }
    brands = allocate_brands(cells, {"AUTOMOVIL": {"A": D(1)}})
    lines = allocate_lines(brands, cells, {("AUTOMOVIL", "A"): {"L1": D("0.5"), "L2": D("0.5")}})
    # N_b = 2 over both municipalities: exact 1 + 1 (one municipality alone could not split)
    assert counts(lines) == {
        (2026, 10, "D", "01", "AUTOMOVIL", "A", "L1"): 1,
        (2026, 10, "D", "01", "AUTOMOVIL", "A", "L2"): 1,
    }


def test_a_calibrated_brand_without_line_share_is_an_error():
    cells = {(2026, 10, "D", "M", "AUTOMOVIL"): ("01", "01001", "car", 5)}
    brands = allocate_brands(cells, {"AUTOMOVIL": {"A": D(1)}})
    with pytest.raises(ValueError):
        allocate_lines(brands, cells, {})

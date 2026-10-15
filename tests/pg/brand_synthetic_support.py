"""Reference model of the synthetic brand/line breakdown (D142, D143, D144 a) in plain Python.

No SQL, no database, no dbt: only `decimal` and the standard library, so the offline tests can
import it too. It is the independent oracle the pg tests compare the three marts against.

Largest remainder (Hamilton), two stages (D143):
  quota q_k = round(N * share_k, 12)   (Postgres round(numeric, 12) rounds half away from zero,
                                        which for positive values is Decimal ROUND_HALF_UP; the
                                        product N * share is exact in both, so they agree)
  base  f_k = floor(q_k),  R = N - sum(f_k)
  the R keys with the largest (q_k - f_k), then the largest q_k, then the smallest key by code
  point (Postgres collation "C" = UTF-8 byte order = code point order) get +1; zeros are dropped.
Class without share (D144 a): one row with key 'SIN CALIBRACION' carrying the whole N.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from decimal import ROUND_HALF_UP, Decimal, localcontext

UNCALIBRATED = "SIN CALIBRACION"
QUANTUM = Decimal("1e-12")
_PRECISION = 120  # far above the digits of any N * share, so the product is never rounded


def quota(total: int, share: Decimal) -> Decimal:
    """round(N * share, 12), half up."""
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        return (Decimal(total) * Decimal(share)).quantize(QUANTUM, rounding=ROUND_HALF_UP)


def hamilton(total: int, shares: Mapping[str, Decimal]) -> dict[str, tuple[int, Decimal]]:
    """Allocate `total` over `shares` -> {key: (count, quota)}, only keys with count > 0.

    The result does not depend on the iteration order of `shares`.
    """
    if total < 0:
        raise ValueError("total must be >= 0")
    quotas = {k: quota(total, s) for k, s in shares.items()}
    base = {k: math.floor(q) for k, q in quotas.items()}
    remaining = total - sum(base.values())
    order = sorted(quotas, key=lambda k: (-(quotas[k] - base[k]), -quotas[k], k))
    out: dict[str, tuple[int, Decimal]] = {}
    for rank, k in enumerate(order, start=1):
        count = base[k] + (1 if rank <= remaining else 0)
        if count > 0:
            out[k] = (count, quotas[k])
    return out


def build_cells(fleet_rows: Iterable[tuple]) -> dict[tuple, tuple]:
    """Cells of the LATEST publication, PARTICULAR segment, from fct_parts_demand_fleet rows.

    Each input row: (publication_year, publication_month, department_name_norm,
    municipality_name_norm, vehicle_class_norm, dane_department_code, dane_municipality_code,
    vehicle_group, demand_segment, active_vehicle_count); the registration year is already summed
    out by the caller or simply repeated rows (rows of the same cell add up).
    Returns {(pub_y, pub_m, dept, muni, cls): (dane_dept, dane_muni, group, N)}.
    """
    rows = list(fleet_rows)
    if not rows:
        return {}
    latest = max(r[0] * 100 + r[1] for r in rows)
    cells: dict[tuple, list] = {}
    for py, pm, dept, muni, cls, dcode, mcode, group, segment, n in rows:
        if py * 100 + pm != latest or segment != "particular":
            continue
        key = (py, pm, dept, muni, cls)
        cell = cells.setdefault(key, [dcode, mcode, group, 0])
        cell[3] += n
    return {k: tuple(v) for k, v in cells.items()}


def allocate_brands(
    cells: Mapping[tuple, tuple], brand_shares: Mapping[str, Mapping[str, Decimal]]
) -> dict[tuple, tuple[int, Decimal]]:
    """Brand stage. `brand_shares` = {class: {brand: pooled_share}} only for calibrated classes.

    Returns {(pub_y, pub_m, dept, muni, cls, brand): (count, quota)}.
    """
    out: dict[tuple, tuple[int, Decimal]] = {}
    for key, (_d, _m, _g, n) in cells.items():
        cls = key[4]
        if cls not in brand_shares:
            if n > 0:
                out[(*key, UNCALIBRATED)] = (n, Decimal(n))
            continue
        for brand, (count, q) in hamilton(n, brand_shares[cls]).items():
            out[(*key, brand)] = (count, q)
    return out


def allocate_lines(
    brand_rows: Mapping[tuple, tuple[int, Decimal]],
    cells: Mapping[tuple, tuple],
    line_shares: Mapping[tuple[str, str], Mapping[str, Decimal]],
) -> dict[tuple, tuple[int, Decimal]]:
    """Line stage. `line_shares` = {(class, brand): {line: pooled_line_share_in_brand}}.

    N_b = sum over municipalities of the brand counts of (pub, department, class, brand).
    Returns {(pub_y, pub_m, dept, dane_dept, cls, brand, line): (count, quota)}.
    """
    totals: dict[tuple, int] = defaultdict(int)
    for (py, pm, dept, muni, cls, brand), (count, _q) in brand_rows.items():
        dane_dept = cells[(py, pm, dept, muni, cls)][0]
        totals[(py, pm, dept, dane_dept, cls, brand)] += count
    out: dict[tuple, tuple[int, Decimal]] = {}
    for key, n_b in totals.items():
        cls, brand = key[4], key[5]
        if brand == UNCALIBRATED:
            out[(*key, UNCALIBRATED)] = (n_b, Decimal(n_b))
            continue
        if (cls, brand) not in line_shares:
            raise ValueError(f"calibrated brand without line share: {cls}/{brand}")
        for line, (count, q) in hamilton(n_b, line_shares[(cls, brand)]).items():
            out[(*key, line)] = (count, q)
    return out

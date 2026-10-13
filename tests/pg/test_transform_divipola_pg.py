"""DIVIPOLA staging and dimension through the real dbt (D125): numeric coordinates, normalized keys,
uniqueness, sanity tests, and "a failed test leaves the previous dimension intact".
"""

from __future__ import annotations

import re
from decimal import Decimal

import divipola_dbt_support as ds
import psycopg
import pytest
from divipola_dbt_support import reader_rows

# Fixtures re-exposed by assignment (pytest finds them by attribute name).
warehouse = ds.warehouse
fleet = ds.fleet
transform = ds.transform
build_divipola = ds.build_divipola

_DIM = (
    "SELECT dane_municipality_code, dane_department_code, department_name, municipality_name, "
    "department_name_norm, municipality_name_norm, municipality_type, longitude, latitude "
    "FROM marts.dim_municipality ORDER BY 1"
)
N_ROWS = len(ds.divipola_rows())


def test_build_creates_the_dimension_with_numeric_coordinates_and_norm_keys(fleet, transform):
    settings = fleet[0]
    code, output = build_divipola(transform)
    assert code == 0, output
    rows = reader_rows(settings, _DIM)
    assert len(rows) == N_ROWS
    by_code = {r[0]: r for r in rows}
    bogota = by_code["11001"]
    assert bogota[1:] == (
        "11",
        "BOGOTÁ, D.C.",
        "BOGOTÁ, D.C.",
        "BOGOTA, D.C.",
        "BOGOTA, D.C.",
        "Municipio",
        Decimal("-74.106992"),
        Decimal("4.649251"),
    )
    san_andres = by_code["88001"]
    assert san_andres[4:8] == (
        "ARCHIPIELAGO DE SAN ANDRES, PROVIDENCIA Y SANTA CATALINA",
        "SAN ANDRES",
        "Isla",
        Decimal("-81.707181"),
    )
    assert by_code["91263"][6] == "Área no municipalizada"
    assert by_code["91263"][8] == Decimal("-1.7")  # negative latitude survives the conversion
    again = transform("build", select="tag:divipola")
    assert again[0] == 0, again[1]
    assert reader_rows(settings, _DIM) == rows  # idempotent


def test_the_stg_view_stays_invisible_to_the_reader(fleet, transform):
    settings = fleet[0]
    assert build_divipola(transform)[0] == 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        reader_rows(settings, "SELECT 1 FROM staging.stg_divipola_municipality")


def test_normalized_name_collision_fails_staging_and_keeps_the_dimension(fleet, transform):
    settings = fleet[0]
    admin = fleet[2]
    assert build_divipola(transform)[0] == 0
    before = reader_rows(settings, _DIM)
    # Landing accepts both names (different text); only the normalized key collides.
    admin.execute(
        "INSERT INTO landing.divipola_municipality SELECT department_code, department_name, "
        "'05999', 'MEDELLIN', municipality_type, longitude, latitude, source_system, "
        "source_reference, load_id FROM landing.divipola_municipality "
        "WHERE municipality_code = '05001'"
    )
    code, output = transform("build", select="tag:divipola")
    assert code == 1
    assert "unique_combination_of_columns_stg_divipola_municipality" in output
    assert re.search(r"SKIP.*dim_municipality", output)
    assert reader_rows(settings, _DIM) == before


def test_out_of_range_coordinates_fail_and_keep_the_dimension(fleet, transform):
    settings = fleet[0]
    admin = fleet[2]
    assert build_divipola(transform)[0] == 0
    before = reader_rows(settings, _DIM)
    admin.execute(
        "UPDATE landing.divipola_municipality SET latitude = '75,0' "
        "WHERE municipality_code = '11001'"
    )
    code, output = transform("build", select="tag:divipola")
    assert code == 1 and "assert_divipola_coordinates_range" in output
    assert re.search(r"SKIP.*dim_municipality", output)
    assert reader_rows(settings, _DIM) == before


def test_truncated_snapshot_fails_the_size_guard(fleet, transform):
    settings = fleet[0]
    admin = fleet[2]
    assert build_divipola(transform)[0] == 0
    before = reader_rows(settings, _DIM)
    admin.execute("DELETE FROM landing.divipola_municipality WHERE department_code >= '30'")
    code, output = transform("build", select="tag:divipola")
    assert code == 1 and "assert_divipola_min_rows" in output
    assert reader_rows(settings, _DIM) == before


def test_unmapped_character_in_a_name_fails_the_charset_guard(fleet, transform):
    settings = fleet[0]
    admin = fleet[2]
    assert build_divipola(transform)[0] == 0
    before = reader_rows(settings, _DIM)
    admin.execute(
        "UPDATE landing.divipola_municipality SET municipality_name = 'MEDELLÍN @' "
        "WHERE municipality_code = '05001'"
    )
    code, output = transform("build", select="tag:divipola")
    assert code == 1 and "assert_divipola_norm_charset" in output
    assert reader_rows(settings, _DIM) == before

"""RUNT -> DANE mapping and the enriched fleet mart through the real dbt (D126, D127, D128).

The real seed of the repository (the 13 approved exceptions) is used; DIVIPOLA and the RUNT
publication in landing are synthetic (divipola_dbt_support). Seed edits happen on the copy of the
dbt project that the `transform` fixture creates in tmp_path.
"""

from __future__ import annotations

import re

import divipola_dbt_support as ds
import pytest
from divipola_dbt_support import reader_rows

# Fixtures re-exposed by assignment (pytest finds them by attribute name).
warehouse = ds.warehouse
transform = ds.transform
fleet = ds.fleet
build_divipola = ds.build_divipola

_MAP = (
    "SELECT department_name_norm, municipality_name_norm, dane_municipality_code, "
    "dane_department_code, match_method, exception_reason "
    "FROM marts.map_runt_municipality_dane ORDER BY 1, 2"
)
_ENRICHED = (
    "SELECT department_name_norm, municipality_name_norm, vehicle_status, vehicle_count, "
    "dane_municipality_code, dane_department_code, dane_match_method "
    "FROM marts.fct_vehicle_fleet_snapshot_dane ORDER BY 1, 2, 3, 4"
)
_FCT = "SELECT sum(vehicle_count), count(*) FROM marts.fct_vehicle_fleet_snapshot"
TOTAL = sum(r[-1] for r in ds.FLEET)
SEED_HEADER = (
    "department_name_norm,municipality_name_norm,dane_municipality_code,dane_municipality_name,"
    "reason,decision_id\n"
)


def append_seed(transform, *lines: str) -> None:
    path = transform.project / "seeds" / "runt_municipality_dane_exception.csv"
    path.write_text(path.read_text(encoding="utf-8") + "".join(f"{x}\n" for x in lines), "utf-8")


def test_header_of_the_repository_seed_is_the_expected_one():
    path = ds.rn.default_project_dir() / "seeds" / "runt_municipality_dane_exception.csv"
    assert path.read_text(encoding="utf-8").startswith(SEED_HEADER)


def test_build_maps_every_pair_and_keeps_every_cell(fleet, transform):
    settings = fleet[0]
    code, output = build_divipola(transform)
    assert code == 0, output
    by_pair = {(r[0], r[1]): r[2:] for r in reader_rows(settings, _MAP)}
    assert by_pair == {
        ("ANTIOQUIA", "MEDELLIN"): ("05001", "05", "auto_norm", None),
        ("ANTIOQUIA", "DON MATIAS"): ("05237", "05", "curated", "official_name_differs"),
        ("BOGOTA D.C.", "BOGOTA"): ("11001", "11", "curated", "official_name_differs"),
        ("VALLE DEL CAUCA", "CALI"): ("76001", "76", "curated", "official_name_differs"),
        ("BOLIVAR", "SANTA ROSA"): ("13683", "13", "auto_norm", None),
        ("CAUCA", "SANTA ROSA"): ("19701", "19", "auto_norm", None),
        ("TOLIMA", "PUEBLITO"): (None, None, None, None),
    }
    enriched = reader_rows(settings, _ENRICHED)
    fct_total, fct_rows = reader_rows(settings, _FCT)[0]
    assert (len(enriched), sum(r[3] for r in enriched)) == (fct_rows, fct_total) == (8, TOTAL)
    unmatched = [r for r in enriched if r[4] is None]
    assert [(r[1], r[3], r[5], r[6]) for r in unmatched] == [("PUEBLITO", 5, None, None)]
    assert "assert_runt_dane_unmatched_pairs" in output and "WARN" in output
    assert "assert_runt_dane_exception_name_matches" not in re.findall(r"WARN \d+ (\S+)", output)
    again = transform("build", select="tag:divipola")
    assert again[0] == 0, again[1]
    assert reader_rows(settings, _ENRICHED) == enriched  # idempotent


def test_the_rut_build_reuses_the_existing_dimension(fleet, transform):
    settings = fleet[0]
    assert build_divipola(transform)[0] == 0
    before = reader_rows(settings, _ENRICHED)
    code, output = transform("build", select="tag:vehicle_fleet")
    assert code == 0, output
    assert "fct_vehicle_fleet_snapshot_dane" in output and "map_runt_municipality_dane" in output
    assert "stg_divipola_municipality" not in output  # DIVIPOLA nodes are not rebuilt
    assert reader_rows(settings, _ENRICHED) == before


def test_without_a_dimension_the_fleet_fct_is_built_and_only_the_dane_mart_fails(fleet, transform):
    settings = fleet[0]
    code, output = transform("build", select="tag:vehicle_fleet")
    assert code == 1
    assert "ERROR assert_runt_dane_exception_code_exists" in output  # no dimension to read
    assert re.search(r"SKIP.*map_runt_municipality_dane", output)
    assert re.search(r"SKIP.*fct_vehicle_fleet_snapshot_dane", output)
    assert reader_rows(settings, _FCT)[0] == (TOTAL, 8)  # the D100 fct is not blocked


def test_unmatched_big_municipality_stops_the_enriched_mart_but_not_the_fct(fleet, transform):
    settings, _, admin = fleet
    assert build_divipola(transform)[0] == 0
    before = reader_rows(settings, _ENRICHED)
    # The unmatched pair grows to far above 1 % of the vehicles; the fct must still follow.
    admin.execute(
        "UPDATE landing.vehicle_fleet_snapshot SET vehicle_count = 5000 "
        "WHERE municipality_name = 'PUEBLITO'"
    )
    code, output = transform("build", select="tag:vehicle_fleet")
    assert code == 1
    assert "assert_runt_dane_unmatched_vehicle_share" in output
    assert re.search(r"SKIP.*fct_vehicle_fleet_snapshot_dane", output)
    assert reader_rows(settings, _ENRICHED) == before  # previous enriched mart intact
    assert reader_rows(settings, _FCT)[0][0] == TOTAL - 5 + 5000  # the fct moved on


def test_not_in_divipola_exception_keeps_the_row_and_counts_in_the_threshold(fleet, transform):
    settings, _, admin = fleet
    append_seed(transform, "TOLIMA,PUEBLITO,,,not_in_divipola,D126")
    assert build_divipola(transform)[0] == 0
    by_pair = {(r[0], r[1]): r[2:] for r in reader_rows(settings, _MAP)}
    assert by_pair[("TOLIMA", "PUEBLITO")] == (None, None, None, "not_in_divipola")
    admin.execute(
        "UPDATE landing.vehicle_fleet_snapshot SET vehicle_count = 5000 "
        "WHERE municipality_name = 'PUEBLITO'"
    )
    code, output = transform("build", select="tag:vehicle_fleet")
    assert code == 1 and "assert_runt_dane_unmatched_vehicle_share" in output


def test_redundant_exception_only_warns(fleet, transform):
    settings = fleet[0]
    append_seed(transform, "ANTIOQUIA,MEDELLIN,05001,MEDELLÍN,official_name_differs,D126")
    code, output = build_divipola(transform)
    assert code == 0, output
    assert "assert_runt_dane_exception_redundant" in re.findall(r"WARN \d+ (\S+)", output)
    by_pair = {(r[0], r[1]): r[2:] for r in reader_rows(settings, _MAP)}
    assert by_pair[("ANTIOQUIA", "MEDELLIN")][:3] == ("05001", "05", "curated")


@pytest.mark.parametrize(
    ("line", "failing_test"),
    [
        (  # a code that DIVIPOLA does not have
            "TOLIMA,PUEBLITO,99999,NO EXISTE,official_name_differs,D126",
            "assert_runt_dane_exception_code_exists",
        ),
        (  # another code than the automatic match
            "ANTIOQUIA,MEDELLIN,11001,BOGOTÁ,official_name_differs,D126",
            "assert_runt_dane_exception_conflicts_auto",
        ),
        (  # not_in_divipola for a pair that does exist
            "ANTIOQUIA,MEDELLIN,,,not_in_divipola,D126",
            "assert_runt_dane_exception_conflicts_auto",
        ),
        (  # the same key twice
            "BOGOTA D.C.,BOGOTA,11001,BOGOTÁ,official_name_differs,D126",
            "unique_combination_of_columns_runt_municipality_dane_exception",
        ),
        (  # key not in normalized form: it could never match
            "Tolima,Pueblito,73443,SAN SEBASTIÁN DE MARIQUITA,official_name_differs,D126",
            "assert_runt_dane_exception_shape",
        ),
        (  # a code without 5 digits
            "TOLIMA,PUEBLITO,7344,X,official_name_differs,D126",
            "assert_runt_dane_exception_shape",
        ),
        (  # not_in_divipola with a code
            "TOLIMA,PUEBLITO,73443,X,not_in_divipola,D126",
            "assert_runt_dane_exception_shape",
        ),
        (  # an unknown reason
            "TOLIMA,PUEBLITO,73443,X,because,D126",
            "accepted_values_runt_municipality_dane_exception_reason",
        ),
    ],
    ids=[
        "unknown_code",
        "other_code",
        "not_in_divipola_but_exists",
        "duplicate_key",
        "key_not_normalized",
        "short_code",
        "not_in_divipola_with_code",
        "unknown_reason",
    ],
)
def test_bad_exceptions_fail_the_build_and_keep_the_previous_map(
    fleet, transform, line, failing_test
):
    settings = fleet[0]
    assert build_divipola(transform)[0] == 0
    before = (reader_rows(settings, _MAP), reader_rows(settings, _ENRICHED))
    append_seed(transform, line)
    code, output = transform("build", select="tag:divipola")
    assert code == 1
    assert failing_test in output
    assert re.search(r"SKIP.*map_runt_municipality_dane", output)
    assert (reader_rows(settings, _MAP), reader_rows(settings, _ENRICHED)) == before


def test_leading_zero_codes_survive_the_seed(fleet, transform):
    settings = fleet[0]
    assert build_divipola(transform)[0] == 0
    codes = {r[1]: r[2] for r in reader_rows(settings, _MAP)}
    assert codes["DON MATIAS"] == "05237"  # text, not the number 5237

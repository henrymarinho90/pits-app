"""Parts-demand marts through the real dbt (D132, D133, D134).

The real class seed of the repository is used; DIVIPOLA and the RUNT publications in landing are
synthetic (divipola_dbt_support). Seed edits happen on the copy of the dbt project that the
`transform` fixture creates in tmp_path.
"""

from __future__ import annotations

import re
import uuid

import divipola_dbt_support as ds
import psycopg
import pytest
from divipola_dbt_support import reader_rows

# Fixtures re-exposed by assignment (pytest finds them by attribute name).
warehouse = ds.warehouse
transform = ds.transform
build_divipola = ds.build_divipola

# (department, municipality, service, status, class, registration_year, count) as the RUNT writes
# them. Every status/service combination of D134 appears; CAMION and CAMIÓN are one key (D100);
# TOLIMA/PUEBLITO has no DANE code (D128); 1900 and 1901 are RUNT sentinels (kept as they are).
DEMAND = [
    ("ANTIOQUIA", "MEDELLIN", "PARTICULAR", "ACTIVO", "AUTOMOVIL", 2020, 1000),
    ("ANTIOQUIA", "MEDELLIN", "PARTICULAR", "ACTIVO", "CAMION", 2018, 10),
    ("ANTIOQUIA", "MEDELLIN", "PARTICULAR", "ACTIVO", "CAMIÓN", 2018, 5),
    ("ANTIOQUIA", "MEDELLIN", "PÚBLICO", "ACTIVO", "BUS", 2015, 40),
    ("ANTIOQUIA", "MEDELLIN", "PÚBLICO", "ACTIVO", "SIN CLASE", 1900, 3),
    ("ANTIOQUIA", "MEDELLIN", "PARTICULAR", "ACTIVO", "EXCAVADORA", 1901, 2),
    ("ANTIOQUIA", "MEDELLIN", "PARTICULAR", "INCONSISTENTE", "AUTOMOVIL", 2020, 7),
    ("ANTIOQUIA", "MEDELLIN", "OFICIAL", "ACTIVO", "AUTOMOVIL", 2020, 11),
    ("ANTIOQUIA", "MEDELLIN", "OTROS", "ACTIVO", "AUTOMOVIL", 2020, 13),
    ("ANTIOQUIA", "MEDELLIN", "NO REGISTRA", "ACTIVO", "AUTOMOVIL", 2020, 17),
    ("ANTIOQUIA", "MEDELLIN", "OFICIAL", "INCONSISTENTE", "AUTOMOVIL", 2020, 19),
    ("TOLIMA", "PUEBLITO", "PARTICULAR", "ACTIVO", "AUTOMOVIL", 2019, 5),
]
TOTAL = sum(r[-1] for r in DEMAND)  # 1132
INCLUDED = 1000 + 10 + 5 + 40 + 3 + 2 + 5  # 1065
EXCLUDED = {
    "excluded_status_inconsistente": 7 + 19,  # status is evaluated before service
    "excluded_service_oficial": 11,
    "excluded_service_otros": 13,
    "excluded_service_no_registra": 17,
}

_RUN_SQL = (
    "INSERT INTO ops.load_run (dataset, source_system, input_fingerprint, transform_name, "
    "rules_version, manifest_key, manifest_sha256, csv_key, csv_sha256, csv_size_bytes, "
    "row_count, coverage_from, coverage_to, last_input_batch_id, last_input_extraction_date, "
    "last_input_finished_at, normalized_manifest, loader_version) VALUES "
    "('vehicle_fleet_snapshot', 'mintransporte_runt_parque', %s, 't', '1', 'k', %s, 'c', %s, 1, "
    "%s, %s, %s, %s, '2026-10-12', now(), '{}'::jsonb, '0.1') RETURNING load_id"
)
_ROW_SQL = (
    "INSERT INTO landing.vehicle_fleet_snapshot VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, "
    "'mintransporte_runt_parque', %s, %s)"
)
_FLEET = (
    "SELECT publication_year, publication_month, department_name_norm, municipality_name_norm, "
    "service_name, vehicle_class_norm, registration_year, dane_department_code, "
    "dane_municipality_code, dane_match_method, demand_segment, vehicle_group, "
    "active_vehicle_count, load_id FROM marts.fct_parts_demand_fleet ORDER BY 1, 2, 3, 4, 5, 6, 7"
)
_SCOPE = (
    "SELECT publication_year, publication_month, scope_status, vehicle_count "
    "FROM marts.fct_parts_demand_scope ORDER BY 1, 2, 3"
)


def load_publication(loader, rows, year=2026, month=10) -> int:
    digest = uuid.uuid4().hex * 2
    start = f"{year}-{month:02d}-01"
    load_id = loader.execute(
        _RUN_SQL, (digest, digest, digest, len(rows), start, start, str(uuid.uuid4()))
    ).fetchone()[0]
    for i, row in enumerate(rows):
        loader.execute(_ROW_SQL, (year, month, *row, f"raw/demand-{year}-{month}#{i}", load_id))
    return load_id


@pytest.fixture
def demand(warehouse):
    """The DIVIPOLA warehouse plus the DEMAND publication (2026-10): (settings, loader, admin)."""
    load_publication(warehouse[1], DEMAND)
    return warehouse


def _scope(settings) -> dict[tuple[int, int, str], int]:
    return {(r[0], r[1], r[2]): r[3] for r in reader_rows(settings, _SCOPE)}


def test_every_class_enters_and_only_active_public_and_private_vehicles(demand, transform):
    settings = demand[0]
    code, output = build_divipola(transform)
    assert code == 0, output
    rows = reader_rows(settings, _FLEET)
    by_key = {(r[4], r[5], r[6]): r for r in rows}
    # No class filter: a car, a heavy vehicle, machinery and "no class" are all there.
    assert by_key[("PARTICULAR", "AUTOMOVIL", 2020)][11:13] == ("car", 1000)
    assert by_key[("PÚBLICO", "BUS", 2015)][10:13] == ("fleet", "heavy", 40)
    assert by_key[("PARTICULAR", "EXCAVADORA", 1901)][11:13] == ("machinery", 2)
    assert by_key[("PÚBLICO", "SIN CLASE", 1900)][11:13] == ("other", 3)  # sentinel year kept
    assert sum(r[12] for r in rows) == INCLUDED
    assert {r[4] for r in rows} == {"PARTICULAR", "PÚBLICO"}
    assert {r[10] for r in rows} == {"particular", "fleet"}
    # INCONSISTENTE (7, 19), OFICIAL (11), OTROS (13) and NO REGISTRA (17) are out: AUTOMOVIL 2020
    # keeps only the 1000 of the ACTIVO PARTICULAR cell.
    assert sum(r[12] for r in rows if r[5] == "AUTOMOVIL" and r[6] == 2020) == 1000


def test_camion_and_accented_camion_are_one_row(demand, transform):
    settings = demand[0]
    assert build_divipola(transform)[0] == 0
    camion = [r for r in reader_rows(settings, _FLEET) if r[5] == "CAMION"]
    assert len(camion) == 1
    assert (camion[0][12], camion[0][11]) == (15, "heavy")


def test_a_pair_without_dane_code_is_kept_with_nulls(demand, transform):
    settings = demand[0]
    code, output = build_divipola(transform)
    assert code == 0, output
    pueblito = [r for r in reader_rows(settings, _FLEET) if r[3] == "PUEBLITO"]
    assert [(r[7], r[8], r[9], r[12]) for r in pueblito] == [(None, None, None, 5)]
    medellin = {r[8:10] for r in reader_rows(settings, _FLEET) if r[3] == "MEDELLIN"}
    assert medellin == {("05001", "auto_norm")}


def test_the_scope_mart_conserves_the_total_and_names_every_exclusion(demand, transform):
    settings = demand[0]
    assert build_divipola(transform)[0] == 0
    scope = _scope(settings)
    assert scope == {(2026, 10, "included"): INCLUDED} | {
        (2026, 10, status): count for status, count in EXCLUDED.items()
    }
    assert sum(scope.values()) == TOTAL  # exact conservation
    fleet_total = sum(r[12] for r in reader_rows(settings, _FLEET))
    assert scope[(2026, 10, "included")] == fleet_total


def test_a_new_class_warns_goes_unmapped_and_keeps_the_totals(warehouse, transform):
    settings, loader, _ = warehouse
    new_class = ("ANTIOQUIA", "MEDELLIN", "PARTICULAR", "ACTIVO", "NUEVA CLASE", 2024, 9)
    load_publication(loader, [*DEMAND, new_class])
    code, output = build_divipola(transform)
    assert code == 0, output
    assert "assert_demand_class_unmapped" in re.findall(r"WARN \d+ (\S+)", output)
    rows = reader_rows(settings, _FLEET)
    unmapped = [r for r in rows if r[11] == "unmapped"]
    assert [(r[5], r[12]) for r in unmapped] == [("NUEVA CLASE", 9)]
    assert sum(r[12] for r in rows) == INCLUDED + 9  # the vehicles are not dropped
    scope = _scope(settings)
    assert sum(scope.values()) == TOTAL + 9
    assert scope[(2026, 10, "included")] == INCLUDED + 9


def test_without_a_new_class_the_unmapped_test_does_not_warn(demand, transform):
    code, output = build_divipola(transform)
    assert code == 0, output
    assert "assert_demand_class_unmapped" not in re.findall(r"WARN \d+ (\S+)", output)


def test_two_publications_coexist_and_keep_their_own_load_id(demand, transform):
    settings, loader, _ = demand
    september = [r for r in DEMAND if r[2] == "PARTICULAR" and r[3] == "ACTIVO"]
    load_publication(loader, september, month=9)
    code, output = build_divipola(transform)
    assert code == 0, output
    scope = _scope(settings)
    sep_total = sum(r[-1] for r in september)
    assert sum(v for k, v in scope.items() if k[1] == 9) == sep_total
    assert sum(v for k, v in scope.items() if k[1] == 10) == TOTAL
    rows = reader_rows(settings, _FLEET)
    load_ids = {m: {r[13] for r in rows if r[1] == m} for m in (9, 10)}
    assert all(len(ids) == 1 for ids in load_ids.values())
    assert load_ids[9] != load_ids[10]
    assert sum(r[12] for r in rows if r[1] == 9) == sep_total


def test_the_second_build_is_idempotent(demand, transform):
    settings = demand[0]
    assert build_divipola(transform)[0] == 0
    fleet, scope = reader_rows(settings, _FLEET), reader_rows(settings, _SCOPE)
    again = transform("build", select="tag:parts_demand")
    assert again[0] == 0, again[1]
    assert (reader_rows(settings, _FLEET), reader_rows(settings, _SCOPE)) == (fleet, scope)
    full = transform("build", select="tag:divipola")
    assert full[0] == 0, full[1]
    assert (reader_rows(settings, _FLEET), reader_rows(settings, _SCOPE)) == (fleet, scope)


def test_reader_sees_the_marts_but_not_staging_or_the_class_seed(demand, transform):
    settings = demand[0]
    assert build_divipola(transform)[0] == 0
    assert reader_rows(settings, "SELECT count(*) FROM marts.fct_parts_demand_fleet")[0][0] > 0
    assert reader_rows(settings, "SELECT count(*) FROM marts.fct_parts_demand_scope")[0][0] == 5
    for relation in ("staging.stg_vehicle_fleet_snapshot", "staging.vehicle_class_demand_scope"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            reader_rows(settings, f"SELECT 1 FROM {relation}")

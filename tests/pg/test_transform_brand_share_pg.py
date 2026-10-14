"""Regional brand/line share marts through the real dbt (D139, D140).

The real seeds of the repository are used; DIVIPOLA, the RUNT publications and the two regional
snapshots in landing are synthetic (brand_share_support). The expected values come from an
independent Python model of D140 (no SQL), not from the marts.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal

import brand_share_support as bs
import pytest
from brand_share_support import BOYACA, RISARALDA, reader_rows

# Fixtures re-exposed by assignment (pytest finds them by attribute name).
warehouse = bs.warehouse
transform = bs.transform

TOL = Decimal("1e-9")
_BRAND = (
    "SELECT source_system, vehicle_class_norm, brand_norm, vehicle_count, region_class_total, "
    "regional_share, region_weight, pooled_weight, pooled_vehicle_count, pooled_share, "
    "pooling_status, sample_size_ok, calibration_scope, source_systems, rows_updated_min::text, "
    "rows_updated_max::text, weight_publication_year, weight_publication_month "
    "FROM marts.fct_regional_brand_share ORDER BY 1, 2, 3"
)
_LINE = (
    "SELECT source_system, vehicle_class_norm, brand_norm, line_norm, vehicle_count, "
    "regional_share, pooled_share, pooled_brand_share, pooled_line_share_in_brand, pooling_status "
    "FROM marts.fct_regional_line_share ORDER BY 1, 2, 3, 4"
)
_WEIGHT = (
    "SELECT source_system, dane_department_code, vehicle_class_norm, weight_vehicle_count, "
    "weight_publication_year, weight_publication_month FROM marts.fct_regional_brand_weight "
    "ORDER BY 1, 3"
)
_SCOPE = (
    "SELECT source_system, scope_status, vehicle_count FROM marts.fct_regional_fleet_brand_scope "
    "ORDER BY 1, 2"
)


def warns(output: str) -> set[str]:
    return set(re.findall(r"WARN \d+ (\S+)", output))


@pytest.fixture
def built(warehouse, transform):
    """Everything built: the documented bootstrap, then the fleet_brand build."""
    assert bs.build_divipola(transform)[0] == 0
    code, output = transform("build", select="tag:fleet_brand")
    assert code == 0, output
    return warehouse[0], output


def close(a, b):
    return abs(Decimal(a) - Decimal(b)) <= TOL


def test_weights_use_only_the_latest_publication_active_particular(built):
    settings, _ = built
    weights, _ = bs.expected_shares()
    rows = reader_rows(settings, _WEIGHT)
    assert {(r[0], r[2]): r[3] for r in rows} == dict(weights)
    assert {r[1] for r in rows} == {"15", "66"}
    assert {(r[4], r[5]) for r in rows} == {(2026, 10)}  # not the 99,999 of 2026-09
    assert dict(weights)[(BOYACA, "AUTOMOVIL")] == 3000


def test_brand_share_matches_the_independent_model(built):
    settings, _ = built
    weights, counts = bs.expected_shares()
    pooled = bs.pooled(counts, weights, "brand")
    rows = reader_rows(settings, _BRAND)
    got = {(r[0], r[1], r[2]): r for r in rows}
    brand_counts: dict[tuple, int] = {}
    for (source, cls, brand, _line), n in counts.items():
        brand_counts[(source, cls, brand)] = brand_counts.get((source, cls, brand), 0) + n
    for (source, cls, brand), n in brand_counts.items():
        assert got[(source, cls, brand)][3] == n
    for r in rows:
        source, cls, brand = r[:3]
        total = sum(v for (s, c, _), v in brand_counts.items() if (s, c) == (source, cls))
        assert r[4] == total and close(r[5], Decimal(r[3]) / total)
        want = pooled[(cls, brand)]
        if want is None:
            assert r[9] is None and r[10] == "no_runt_weight"
        else:
            assert close(r[9], want) and r[10] == "ok"
        assert r[12] == "regional"
    # A brand absent from a region that has the class shows up there with 0 vehicles.
    assert got[(RISARALDA, "AUTOMOVIL", "MARCA B")][3] == 0
    assert got[(BOYACA, "AUTOMOVIL", "MARCA C")][3] == 0


def test_line_share_matches_the_independent_model(built):
    settings, _ = built
    weights, counts = bs.expected_shares()
    pooled_line = bs.pooled(counts, weights, "line")
    pooled_brand = bs.pooled(counts, weights, "brand")
    rows = reader_rows(settings, _LINE)
    got = {r[:4]: r for r in rows}
    for key, n in counts.items():
        assert got[key][4] == n
    for r in rows:
        source, cls, brand, line = r[:4]
        want = pooled_line[(cls, brand, line)]
        if want is None:
            assert r[6] is None and r[8] is None and r[9] == "no_runt_weight"
            continue
        assert close(r[6], want) and close(r[7], pooled_brand[(cls, brand)])
        if pooled_brand[(cls, brand)] > 0:
            assert close(r[8], want / pooled_brand[(cls, brand)])


def test_pooled_value_is_weighted_by_the_runt_not_by_the_sample(built):
    settings, _ = built
    rows = {(r[0], r[1], r[2]): r for r in reader_rows(settings, _BRAND)}
    # AUTOMOVIL: Boyaca 90/110 A (w 3000), Risaralda 40/105 A (w 1000): hand-computed.
    boyaca_a = Decimal(90) / 110
    risaralda_a = Decimal(40) / 105
    want = (3000 * boyaca_a + 1000 * risaralda_a) / 4000
    row = rows[(BOYACA, "AUTOMOVIL", "MARCA A")]
    assert close(row[9], want) and row[7] == 4000 and row[8] == 130
    assert row[13] == f"{BOYACA},{RISARALDA}"
    assert (row[14], row[15]) == ("2026-07-06", "2026-07-06")
    assert (row[16], row[17]) == (2026, 10)
    assert row[11] is False  # 130 pooled vehicles < 1,000


def test_sample_size_flag_uses_a_threshold_of_1000(warehouse, transform):
    settings, loader, admin = warehouse
    admin.execute(
        "DELETE FROM landing.regional_fleet_brand_count WHERE source_system = %s", (BOYACA,)
    )
    big = [("AUTOMOVIL", "MARCA BIG", "B1", "PARTICULAR", "ACTIVO", 1000)]
    bs.load_regional(loader, BOYACA, [*bs.BOYACA_ROWS, *big], rows_updated="2026-07-07")
    assert bs.build_divipola(transform)[0] == 0
    code, output = transform("build", select="tag:fleet_brand")
    assert code == 0, output
    rows = {(r[0], r[1], r[2]): r for r in reader_rows(settings, _BRAND)}
    assert rows[(BOYACA, "AUTOMOVIL", "MARCA BIG")][11] is True  # exactly 1,000
    assert rows[(BOYACA, "AUTOMOVIL", "MARCA B")][11] is False


def test_auteco_resolution_alias_map_and_sin_asignar(built):
    settings, output = built
    rows = {(r[0], r[1], r[2]): r for r in reader_rows(settings, _BRAND)}
    assert not any(r[2] == "AUTECO" for r in rows.values())
    # BOYACA MOTOCICLETA: alias -> BAJAJ 30; map -> KYMCO 25; SIN ASIGNAR = 5 (explicit row) + 2
    # (line without a row).
    assert rows[(BOYACA, "MOTOCICLETA", "BAJAJ")][3] == 30
    assert rows[(BOYACA, "MOTOCICLETA", "KYMCO")][3] == 25
    assert rows[(BOYACA, "MOTOCICLETA", "SIN ASIGNAR")][3] == 7
    # RISARALDA: AUTECO VICTORY merges with VICTORY; ACTIVE 110 is SIN ASIGNAR.
    assert rows[(RISARALDA, "MOTOCICLETA", "VICTORY")][3] == 120
    assert rows[(RISARALDA, "MOTOCICLETA", "SIN ASIGNAR")][3] == 10
    assert "assert_regional_auteco_unassigned" in warns(output)  # LINEA NUEVA XYZ only


def test_the_explicit_sin_asignar_line_alone_does_not_warn(warehouse, transform):
    settings, loader, admin = warehouse
    admin.execute(
        "DELETE FROM landing.regional_fleet_brand_count WHERE line IN ('LINEA NUEVA XYZ')"
    )
    # keep the manifest total and row_count consistent with the deletion
    admin.execute(
        "UPDATE ops.load_run SET row_count = row_count - 1, normalized_manifest = "
        "jsonb_set(normalized_manifest, '{vehicle_total}', to_jsonb((normalized_manifest->>"
        "'vehicle_total')::int - 2)) WHERE dataset = 'regional_fleet_brand_count' "
        "AND source_system = %s",
        (BOYACA,),
    )
    assert bs.build_divipola(transform)[0] == 0
    code, output = transform("build", select="tag:fleet_brand")
    assert code == 0, output
    assert "assert_regional_auteco_unassigned" not in warns(output)


def test_risaralda_has_null_service_and_status_and_the_scope_is_conserved(built, warehouse):
    settings, _ = built
    stg = (
        warehouse[2]
        .execute(
            "SELECT count(*), count(service_name), count(vehicle_status), "
            "count(service_name_norm), count(vehicle_status_norm) "
            "FROM staging.stg_regional_fleet_brand WHERE source_system = %s",
            (RISARALDA,),
        )
        .fetchone()
    )
    assert stg == (len(bs.RISARALDA_ROWS), 0, 0, 0, 0)
    scope = {(r[0], r[1]): r[2] for r in reader_rows(settings, _SCOPE)}
    assert scope == {
        (BOYACA, "included"): 110 + 25 + 30 + 5 + 2 + 12,
        (BOYACA, "excluded_service"): 15,
        (BOYACA, "excluded_status"): 5,
        (BOYACA, "excluded_class"): 8 + 4,
        (RISARALDA, "included"): 30 + 10 + 60 + 5 + 100 + 20 + 10,
        (RISARALDA, "excluded_class"): 3,
    }
    totals = {BOYACA: sum(r[-1] for r in bs.BOYACA_ROWS), RISARALDA: 238}
    assert sum(v for (s, _), v in scope.items() if s == BOYACA) == totals[BOYACA]
    assert sum(v for (s, _), v in scope.items() if s == RISARALDA) == totals[RISARALDA]


def test_class_without_weight_is_null_and_warns_and_unmapped_class_warns(built):
    settings, output = built
    rows = [r for r in reader_rows(settings, _BRAND) if r[1] == "CAMPERO"]
    assert [(r[0], r[2], r[9], r[10], r[17]) for r in rows] == [
        (BOYACA, "MARCA C", None, "no_runt_weight", None)
    ]
    assert rows[0][5] == 1  # the regional share is still published
    found = warns(output)
    assert {"assert_regional_pooling_no_weight", "assert_regional_class_unmapped"} <= found


def test_every_share_adds_up_to_one(built):
    settings, _ = built
    by_class: dict[str, Decimal] = {}
    for cls, _brand, share in {
        (r[1], r[2], r[9]) for r in reader_rows(settings, _BRAND) if r[10] == "ok"
    }:
        by_class[cls] = by_class.get(cls, Decimal(0)) + share
    assert by_class and all(close(v, 1) for v in by_class.values())
    by_region: dict[tuple, Decimal] = {}
    for r in reader_rows(settings, _LINE):
        by_region[(r[0], r[1])] = by_region.get((r[0], r[1]), Decimal(0)) + r[5]
    assert all(close(v, 1) for v in by_region.values())


def test_the_second_build_is_idempotent(built, transform):
    settings, _ = built
    before = [reader_rows(settings, q) for q in (_BRAND, _LINE, _WEIGHT, _SCOPE)]
    code, output = transform("build", select="tag:fleet_brand")
    assert code == 0, output
    assert [reader_rows(settings, q) for q in (_BRAND, _LINE, _WEIGHT, _SCOPE)] == before


# --- failure modes ----------------------------------------------------------------------------


def test_fresh_database_without_the_demand_mart_fails_only_the_weight_node(warehouse, transform):
    code, output = transform("build", select="tag:fleet_brand")
    assert code == 1
    assert re.search(r"ERROR creating sql table model marts\.fct_regional_brand_weight", output)
    # Everything upstream of the weights was built and passed; everything downstream was skipped.
    assert re.search(r"OK created sql view model staging\.stg_regional_fleet_brand", output)
    assert "ERROR creating sql table model marts.fct_regional_brand_share" not in output
    assert "ERROR creating sql table model marts.fct_regional_fleet_brand_scope" not in output
    assert re.search(r"SKIP relation marts\.fct_regional_brand_share", output)
    admin = warehouse[2]
    marts = {
        r[0]
        for r in admin.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'marts'"
        )
    }
    # The scope mart does not depend on the weights, so it is built; the three that do are not.
    assert {m for m in marts if m.startswith("fct_regional")} == {"fct_regional_fleet_brand_scope"}


def test_a_department_without_weight_fails_and_leaves_the_previous_marts_intact(
    built, transform, warehouse
):
    settings, _ = built
    before = [reader_rows(settings, q) for q in (_BRAND, _LINE, _SCOPE)]
    seed = transform.project / "seeds" / "regional_brand_source.csv"
    seed.write_text(seed.read_text(encoding="utf-8").replace(",66,", ",77,"), encoding="utf-8")
    code, output = transform("build", select="tag:fleet_brand")
    assert code == 1
    assert re.search(r"FAIL \d+ assert_regional_brand_weight_present", output)
    assert [reader_rows(settings, q) for q in (_BRAND, _LINE, _SCOPE)] == before


def test_a_failed_conservation_test_fails_the_build(warehouse, transform):
    admin = warehouse[2]
    assert bs.build_divipola(transform)[0] == 0
    admin.execute(
        "UPDATE ops.load_run SET row_count = row_count + 1 "
        "WHERE dataset = 'regional_fleet_brand_count' AND source_system = %s",
        (BOYACA,),
    )
    code, output = transform("build", select="tag:fleet_brand")
    assert code == 1
    assert re.search(r"FAIL \d+ assert_regional_scope_conserves", output)


def test_an_unknown_source_system_in_landing_fails_staging_and_keeps_the_marts(
    built, transform, warehouse
):
    settings = warehouse[0]
    before = [reader_rows(settings, q) for q in (_BRAND, _LINE, _SCOPE)]
    admin = warehouse[2]
    admin.execute(
        "ALTER TABLE landing.regional_fleet_brand_count "
        "DROP CONSTRAINT regional_fleet_brand_count_source_system_ck"
    )
    admin.execute(
        "UPDATE landing.regional_fleet_brand_count SET source_system = 'otro_sistema' "
        "WHERE line = 'C1'"
    )
    code, output = transform("build", select="tag:fleet_brand")
    assert code == 1
    assert [reader_rows(settings, q) for q in (_BRAND, _LINE, _SCOPE)] == before


# --- independence of the families -------------------------------------------------------------


def test_the_vehicle_fleet_and_divipola_builds_do_not_touch_the_brand_marts(built, transform):
    settings, _ = built
    before = [reader_rows(settings, q) for q in (_BRAND, _LINE, _WEIGHT, _SCOPE)]
    for tag in ("tag:vehicle_fleet", "tag:divipola", "tag:parts_demand"):
        code, output = transform("build", select=tag)
        assert code == 0, output
        assert "regional" not in output and "brand_alias" not in output
    assert [reader_rows(settings, q) for q in (_BRAND, _LINE, _WEIGHT, _SCOPE)] == before


def test_the_vehicle_fleet_build_is_green_without_any_brand_mart(warehouse, transform):
    assert bs.build_divipola(transform)[0] == 0
    marts = {
        r[0]
        for r in warehouse[2].execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'marts'"
        )
    }
    assert "fct_parts_demand_fleet" in marts
    assert not any(m.startswith("fct_regional") for m in marts)


def test_the_brand_seeds_carry_only_their_own_tag_and_no_test_mixes_families(transform):
    code, output = transform("parse")
    assert code == 0, output
    manifest = json.loads((transform.project / "target" / "manifest.json").read_text("utf-8"))
    nodes = {**manifest["nodes"], **manifest["sources"]}

    def tags(uid):
        node = nodes.get(uid, {})
        return set(node.get("tags", [])) | set(node.get("config", {}).get("tags", []))

    seeds = {
        n["name"]: tags(u) for u, n in manifest["nodes"].items() if n["resource_type"] == "seed"
    }
    for name in (
        "regional_brand_source",
        "regional_vehicle_class_map",
        "brand_alias",
        "auteco_line_brand_map",
    ):
        assert seeds[name] == {"fleet_brand"}
    assert seeds["vehicle_class_demand_scope"] == {"vehicle_fleet", "divipola"}
    assert seeds["runt_municipality_dane_exception"] == {"vehicle_fleet", "divipola"}
    foreign = {"vehicle_fleet", "divipola", "parts_demand"}
    checked = 0
    for node in manifest["nodes"].values():
        if node["resource_type"] != "test":
            continue
        families = set(node["config"].get("tags", []))
        for parent in node["depends_on"]["nodes"]:
            families |= tags(parent)
        if "fleet_brand" in families:
            checked += 1
            assert not families & foreign, (node["name"], sorted(families))
    assert checked > 50

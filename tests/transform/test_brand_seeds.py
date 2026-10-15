"""Offline checks of the D139 regional seeds (CSV files only; no dbt, no database)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from pits.sources.brand_fleet.contract import SOURCES

SEEDS = Path(__file__).resolve().parents[2] / "transform" / "seeds"


def rows(name: str) -> list[dict[str, str]]:
    with open(SEEDS / f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_class_map_targets_are_runt_classes_or_excluded():
    runt = {r["vehicle_class_norm"] for r in rows("vehicle_class_demand_scope")}
    for r in rows("regional_vehicle_class_map"):
        assert r["vehicle_class_norm"] == "excluded" or r["vehicle_class_norm"] in runt, r


def test_class_map_covers_both_sources_with_unique_keys():
    keys = [
        (r["source_system"], r["source_class_norm"]) for r in rows("regional_vehicle_class_map")
    ]
    assert len(keys) == len(set(keys))
    assert {k[0] for k in keys} == {s.source_system for s in SOURCES.values()}


def test_brand_source_matches_the_contract_systems_and_codes():
    seed = {r["source_system"]: r["dane_department_code"] for r in rows("regional_brand_source")}
    assert seed == {
        "gobernacion_boyaca_parque_automotor": "15",
        "gobernacion_risaralda_parque_automotor": "66",
    }
    assert set(seed) == {s.source_system for s in SOURCES.values()}


def test_auteco_map_shape():
    data = rows("auteco_line_brand_map")
    assert len(data) == len({r["line_norm"] for r in data}) == 578
    assert {r["evidence"] for r in data} == {"dato", "inferencia", "sin_evidencia"}
    assert all(r["real_brand"] != "AUTECO" for r in data)
    # SIN ASIGNAR is explicit and has no evidence; every assigned brand has some.
    for r in data:
        assert (r["real_brand"] == "SIN ASIGNAR") == (r["evidence"] == "sin_evidencia"), r


def test_alias_never_points_to_auteco_or_to_itself():
    for r in rows("brand_alias"):
        assert r["brand_norm"] not in ("AUTECO", r["source_brand_norm"])


@pytest.mark.parametrize(
    "name",
    ["regional_brand_source", "regional_vehicle_class_map", "brand_alias", "auteco_line_brand_map"],
)
def test_every_row_has_a_decision_and_no_blank_cell(name):
    for r in rows(name):
        assert all(v.strip() == v and v != "" for v in r.values()), r
        assert r["decision_id"] in ("D139", "D140")

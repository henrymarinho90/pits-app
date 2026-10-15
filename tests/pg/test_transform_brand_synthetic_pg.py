"""Synthetic brand/line breakdown marts through the real dbt (D142-D145, hito B).

The expected rows come from the Hamilton model of brand_synthetic_support (plain Python, Decimal,
no SQL); the marts must match it exactly on every row. Inputs of the model are read from the marts
that are not under test (fct_parts_demand_fleet and the regional share marts, already checked
against their own independent model in test_transform_brand_share_pg); the cell sums are also
checked against the hand-written RUNT fixture below.

Cost control: the read-only behaviour tests share ONE database and ONE build (module fixture
`world`, its own database created with the helpers of pg_support). The tests that change state or
need another landing (fresh base, reversed order, skewed fixture) use the per-test fixtures of the
family. All brands, lines and counts are synthetic.
"""

from __future__ import annotations

import re
import subprocess
from collections import namedtuple
from decimal import Decimal

import brand_share_support as bs
import brand_synthetic_support as hm
import divipola_dbt_support as ds
import pg_support
import pytest
from brand_share_support import BOYACA, RISARALDA, reader_rows

from pits.cli import app
from pits.transform import cli as tcli
from pits.warehouse.connection import connect
from pits.warehouse.migrate import run_migrate
from pits.warehouse.settings import Profile

transform = bs.transform

# --- the fixture: brand_share_support plus the cases of hito B ----------------------------------

# Extra RUNT rows of publication 2026-10 (department, municipality, service, status, class, year,
# count). Medellin is not a region: CAMPERO has regional rows but no RUNT weight (no_runt_weight)
# and GRUA is in no region at all -> both are SIN CALIBRACION. The public/inconsistent rows must not
# enter. CAMIONETA has two brands with identical shares (tie) in both regions. The filler
# municipalities of DEPARTAMENTO 30 give cells of 1 and 7 vehicles.
EXTRA_RUNT = [
    ("ANTIOQUIA", "MEDELLIN", "PARTICULAR", "ACTIVO", "CAMPERO", 2018, 40),
    ("ANTIOQUIA", "MEDELLIN", "PÚBLICO", "ACTIVO", "CAMPERO", 2018, 10),
    ("ANTIOQUIA", "MEDELLIN", "PARTICULAR", "ACTIVO", "GRUA", 2018, 7),
    ("ANTIOQUIA", "MEDELLIN", "PARTICULAR", "INCONSISTENTE", "GRUA", 2018, 3),
    ("BOYACA", "TUNJA", "PARTICULAR", "ACTIVO", "CAMIONETA", 2020, 2),
    ("BOYACA", "TUNJA", "PARTICULAR", "ACTIVO", "CAMIONETA", 2015, 1),
    ("RISARALDA", "PEREIRA", "PARTICULAR", "ACTIVO", "CAMIONETA", 2020, 1),
    ("DEPARTAMENTO 30", "MUNICIPIO 30 101", "PARTICULAR", "ACTIVO", "AUTOMOVIL", 2021, 1),
    ("DEPARTAMENTO 30", "MUNICIPIO 30 102", "PARTICULAR", "ACTIVO", "AUTOMOVIL", 2021, 1),
    ("DEPARTAMENTO 30", "MUNICIPIO 30 103", "PARTICULAR", "ACTIVO", "MOTOCICLETA", 2021, 1),
    ("DEPARTAMENTO 30", "MUNICIPIO 30 104", "PARTICULAR", "ACTIVO", "AUTOMOVIL", 2021, 4),
    ("DEPARTAMENTO 30", "MUNICIPIO 30 104", "PARTICULAR", "ACTIVO", "AUTOMOVIL", 2019, 3),
]
CAMIONETA = [
    ("CAMIONETA", "ALFA", "L1", "PARTICULAR", "ACTIVO", 25),
    ("CAMIONETA", "ALFA", "L2", "PARTICULAR", "ACTIVO", 25),
    ("CAMIONETA", "ZETA", "Z1", "PARTICULAR", "ACTIVO", 50),
]
CAMIONETA_RISARALDA = [(c, b, ln, None, None, n) for c, b, ln, _s, _t, n in CAMIONETA]
UNCAL = hm.UNCALIBRATED
PUB = (2026, 10)


def skew_rows(skew):
    """Many 1-vehicle AUTOMOVIL cells: Hamilton gives each to the top brand (drift)."""
    return [
        ("DEPARTAMENTO 30", f"MUNICIPIO 30 {m}", "PARTICULAR", "ACTIVO", "AUTOMOVIL", 2021, 1)
        for m in range(1, skew + 1)
    ]


def load_world(loader, reverse=False, skew=0):
    """Landing of the hito B fixture; `reverse` inserts everything in the opposite order."""
    divipola = [*ds.divipola_rows(), *bs.EXTRA_DIVIPOLA]
    runt = [*bs.RUNT, *EXTRA_RUNT, *skew_rows(skew)]
    boyaca = [*bs.BOYACA_ROWS, *CAMIONETA]
    risaralda = [*bs.RISARALDA_ROWS, *CAMIONETA_RISARALDA]
    if reverse:
        divipola, runt, boyaca, risaralda = (x[::-1] for x in (divipola, runt, boyaca, risaralda))
    ds.load_divipola_landing(loader, divipola)
    bs.load_runt(loader, bs.RUNT_OLD, month=9)
    bs.load_runt(loader, runt)
    bs.load_regional(loader, BOYACA, boyaca)
    bs.load_regional(loader, RISARALDA, risaralda)


@pytest.fixture
def reverse_landing():
    return False


@pytest.fixture
def skew_cells():
    return 0


@pytest.fixture
def warehouse(pg_settings, reverse_landing, skew_cells):
    """Per-test database with the hito B landing (overrides the one of the family by name)."""
    run_migrate(pg_settings)
    loader = connect(pg_settings, Profile.LOADER, autocommit=True)
    admin = connect(pg_settings, Profile.ADMIN, autocommit=True)
    load_world(loader, reverse=reverse_landing, skew=skew_cells)
    yield pg_settings, loader, admin
    loader.close()
    admin.close()


# --- module-scoped world: one database, one bootstrap, one fleet_brand build ---------------------

World = namedtuple("World", "settings admin run output")


class _Dbt:
    """`pits transform` with the settings of the module database; output captured per call."""

    def __init__(self, settings, project):
        self.settings = settings
        self.project = project

    def __call__(self, command, select=None):
        chunks: list[str] = []

        def capture(argv, env):
            proc = subprocess.run(
                list(argv),
                env=dict(env),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            chunks.append(proc.stdout + proc.stderr)
            return proc.returncode

        args = ["transform", command, *(["--select", select] if select else [])]
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(tcli, "project_dir_factory", lambda: self.project)
            mp.setattr(tcli, "settings_factory", lambda env: self.settings)
            mp.setattr(tcli, "dbt_runner", capture)
            result = ds.runner.invoke(app, args)
        return result.exit_code, result.output + "".join(chunks)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    import dataclasses
    import secrets
    import shutil
    import uuid

    from pits.transform import runner as rn
    from pits.warehouse.settings import RoleNames

    base = pg_support._admin_base()
    tag = uuid.uuid4().hex[:8]
    settings = dataclasses.replace(
        base,
        dbname=f"pits_test_{tag}",
        loader_password=secrets.token_urlsafe(24),
        reader_password=secrets.token_urlsafe(24),
        transformer_password=secrets.token_urlsafe(24),
        roles=RoleNames(
            owner=f"pits_owner_t{tag}",
            loader=f"pits_loader_t{tag}",
            reader=f"pits_reader_t{tag}",
            transformer=f"pits_transformer_t{tag}",
        ),
    )
    assert settings.dbname != pg_support.REAL_DB
    project = tmp_path_factory.mktemp("synthetic_world") / "transform"
    shutil.copytree(
        rn.default_project_dir(),
        project,
        ignore=shutil.ignore_patterns("target", "logs", "dbt_packages"),
    )
    admin = None
    try:
        run_migrate(settings)
        loader = connect(settings, Profile.LOADER, autocommit=True)
        try:
            load_world(loader)
        finally:
            loader.close()
        admin = connect(settings, Profile.ADMIN, autocommit=True)
        run = _Dbt(settings, project)
        assert bs.build_divipola(run)[0] == 0
        code, output = run("build", select="tag:fleet_brand")
        assert code == 0, output
        yield World(settings, admin, run, output)
    finally:
        if admin is not None:
            admin.close()
        pg_support._cleanup(settings)


# --- readers ------------------------------------------------------------------------------------

_FLEET = (
    "SELECT publication_year, publication_month, department_name_norm, municipality_name_norm, "
    "vehicle_class_norm, dane_department_code, dane_municipality_code, vehicle_group, "
    "demand_segment, active_vehicle_count FROM marts.fct_parts_demand_fleet"
)
_SHARES = (
    "SELECT DISTINCT vehicle_class_norm, brand_norm, pooled_share, sample_size_ok "
    "FROM marts.fct_regional_brand_share WHERE pooled_share IS NOT NULL"
)
_LINE_SHARES = (
    "SELECT DISTINCT vehicle_class_norm, brand_norm, line_norm, pooled_line_share_in_brand, "
    "sample_size_ok FROM marts.fct_regional_line_share WHERE pooled_line_share_in_brand IS NOT NULL"
)
_CELL = (
    "SELECT publication_year, publication_month, department_name_norm, municipality_name_norm, "
    "vehicle_class_norm, dane_department_code, dane_municipality_code, vehicle_group, "
    "active_vehicle_count, calibration_status FROM marts.fct_synthetic_fleet_cell"
)
_BRAND = (
    "SELECT publication_year, publication_month, department_name_norm, municipality_name_norm, "
    "vehicle_class_norm, brand_norm, synthetic_vehicle_count, allocation_quota, sample_size_ok, "
    "source_systems, rows_updated_min::text, rows_updated_max::text, weight_publication_year, "
    "weight_publication_month, data_origin, calibration_scope, allocation_method, "
    "dane_department_code, dane_municipality_code, vehicle_group "
    "FROM marts.fct_synthetic_brand_fleet"
)
_LINE = (
    "SELECT publication_year, publication_month, department_name_norm, dane_department_code, "
    "vehicle_class_norm, brand_norm, line_norm, synthetic_vehicle_count, allocation_quota, "
    "sample_size_ok, source_systems, rows_updated_min::text, rows_updated_max::text, "
    "weight_publication_year, weight_publication_month, data_origin, calibration_scope, "
    "allocation_method FROM marts.fct_synthetic_line_fleet"
)


def snapshot(settings):
    """The three synthetic marts, sorted, as plain tuples."""
    return [sorted(reader_rows(settings, q), key=repr) for q in (_CELL, _BRAND, _LINE)]


def model(settings):
    """(cells, calibration, brand rows, line rows) of the Python Hamilton model."""
    fleet = hm.build_cells(reader_rows(settings, _FLEET))
    brand_shares: dict[str, dict[str, Decimal]] = {}
    for cls, brand, share, _ok in reader_rows(settings, _SHARES):
        brand_shares.setdefault(cls, {})[brand] = share
    line_shares: dict[tuple, dict[str, Decimal]] = {}
    for cls, brand, line, share, _ok in reader_rows(settings, _LINE_SHARES):
        line_shares.setdefault((cls, brand), {})[line] = share
    brands = hm.allocate_brands(fleet, brand_shares)
    lines = hm.allocate_lines(brands, fleet, line_shares)
    return fleet, brand_shares, brands, lines


def warns(output):
    return set(re.findall(r"WARN \d+ (\S+)", output))


def drifting(settings, threshold=Decimal("0.005")):
    """Classes where |national synthetic share - pooled_share| > threshold (D144 f), in Python."""
    _fleet, brand_shares, brands, _lines = model(settings)
    per_class: dict[str, dict[str, int]] = {}
    for key, (count, _q) in brands.items():
        if key[5] != UNCAL:
            per_class.setdefault(key[4], {}).setdefault(key[5], 0)
            per_class[key[4]][key[5]] += count
    out = set()
    for cls, shares in brand_shares.items():
        total = sum(per_class.get(cls, {}).values())
        if not total:
            continue
        for brand, pooled in shares.items():
            synthetic = Decimal(per_class[cls].get(brand, 0)) / total
            if abs(synthetic - pooled) > threshold:
                out.add(cls)
    return out


def assert_matches_model(settings):
    fleet, brand_shares, brands, lines = model(settings)
    cells = {r[:5]: (r[5], r[6], r[7], r[8], r[9]) for r in reader_rows(settings, _CELL)}
    assert len(cells) == len(reader_rows(settings, _CELL))
    want_cells = {
        k: (*v[:3], v[3], "calibrated" if k[4] in brand_shares else "no_calibration")
        for k, v in fleet.items()
    }
    assert cells == want_cells
    got_brands = {r[:6]: (r[6], r[7]) for r in reader_rows(settings, _BRAND)}
    assert len(got_brands) == len(reader_rows(settings, _BRAND))
    assert got_brands == brands
    got_lines = {(*r[:4], *r[4:7]): (r[7], r[8]) for r in reader_rows(settings, _LINE)}
    assert len(got_lines) == len(reader_rows(settings, _LINE))
    assert got_lines == lines
    return fleet, brands, lines


# --- behaviour ---------------------------------------------------------------------------------


def test_cells_are_the_latest_publication_particular_active_sum_over_years(world):
    cells = {r[:5]: r for r in reader_rows(world.settings, _CELL)}
    got = {k: r[8] for k, r in cells.items()}
    assert got == {
        (*PUB, "BOYACA", "TUNJA", "AUTOMOVIL"): 3000,  # 2000 + 1000 (2020 + 2015), not 99,999
        (*PUB, "BOYACA", "TUNJA", "MOTOCICLETA"): 1000,
        (*PUB, "BOYACA", "TUNJA", "CAMIONETA"): 3,
        (*PUB, "RISARALDA", "PEREIRA", "AUTOMOVIL"): 1000,
        (*PUB, "RISARALDA", "PEREIRA", "MOTOCICLETA"): 3000,
        (*PUB, "RISARALDA", "PEREIRA", "CAMIONETA"): 1,
        (*PUB, "ANTIOQUIA", "MEDELLIN", "CAMPERO"): 40,  # the PUBLICO 10 is not in
        (*PUB, "ANTIOQUIA", "MEDELLIN", "GRUA"): 7,  # the INCONSISTENTE 3 is not in
        (*PUB, "DEPARTAMENTO 30", "MUNICIPIO 30 101", "AUTOMOVIL"): 1,
        (*PUB, "DEPARTAMENTO 30", "MUNICIPIO 30 102", "AUTOMOVIL"): 1,
        (*PUB, "DEPARTAMENTO 30", "MUNICIPIO 30 103", "MOTOCICLETA"): 1,
        (*PUB, "DEPARTAMENTO 30", "MUNICIPIO 30 104", "AUTOMOVIL"): 7,  # 4 + 3
    }
    assert {k[:2] for k in cells} == {PUB}  # the old 2026-09 publication is absent
    assert cells[(*PUB, "BOYACA", "TUNJA", "AUTOMOVIL")][5:8] == ("15", "15001", "car")


def test_the_three_marts_equal_the_python_hamilton_model_on_every_row(world):
    _fleet, brands, lines = assert_matches_model(world.settings)
    assert len(brands) > 20 and len(lines) > 20  # not a vacuous comparison


def test_sums_per_cell_equal_the_runt_recomputed_from_the_demand_mart(world):
    settings = world.settings
    fleet = hm.build_cells(reader_rows(settings, _FLEET))
    sums: dict[tuple, int] = {}
    for r in reader_rows(settings, _BRAND):
        sums[r[:5]] = sums.get(r[:5], 0) + r[6]
    assert sums == {k: v[3] for k, v in fleet.items()}
    # lines add up to their brand per (department, class, brand), and so does the grand total
    brand_totals: dict[tuple, int] = {}
    for r in reader_rows(settings, _BRAND):
        key = (r[0], r[1], r[2], r[4], r[5])
        brand_totals[key] = brand_totals.get(key, 0) + r[6]
    line_totals: dict[tuple, int] = {}
    for r in reader_rows(settings, _LINE):
        key = (r[0], r[1], r[2], r[4], r[5])
        line_totals[key] = line_totals.get(key, 0) + r[7]
    assert line_totals == brand_totals
    assert sum(sums.values()) == sum(v[3] for v in fleet.values())


def test_alphabetical_tie_and_cells_of_one_vehicle(world):
    brands = {r[:6]: r[6:8] for r in reader_rows(world.settings, _BRAND)}
    # CAMIONETA pooled 0.5 / 0.5, N = 3: quotas 1.5 / 1.5, the extra unit goes to ALFA < ZETA
    assert brands[(*PUB, "BOYACA", "TUNJA", "CAMIONETA", "ALFA")] == (2, Decimal("1.5"))
    assert brands[(*PUB, "BOYACA", "TUNJA", "CAMIONETA", "ZETA")] == (1, Decimal("1.5"))
    # N = 1: one vehicle to the alphabetical first of the tie, the other brand has no row
    assert brands[(*PUB, "RISARALDA", "PEREIRA", "CAMIONETA", "ALFA")] == (1, Decimal("0.5"))
    assert (*PUB, "RISARALDA", "PEREIRA", "CAMIONETA", "ZETA") not in brands
    # line stage, department level: Boyaca N_b = 2 splits 1 + 1; Risaralda N_b = 1 -> L1 only
    lines = {(r[2], r[4], r[5], r[6]): r[7] for r in reader_rows(world.settings, _LINE)}
    assert lines[("BOYACA", "CAMIONETA", "ALFA", "L1")] == 1
    assert lines[("BOYACA", "CAMIONETA", "ALFA", "L2")] == 1
    assert lines[("BOYACA", "CAMIONETA", "ZETA", "Z1")] == 1
    assert lines[("RISARALDA", "CAMIONETA", "ALFA", "L1")] == 1
    assert ("RISARALDA", "CAMIONETA", "ALFA", "L2") not in lines
    # N = 1 AUTOMOVIL cells: exactly one brand row with 1 vehicle each
    for muni in ("MUNICIPIO 30 101", "MUNICIPIO 30 102"):
        rows = [r for r in reader_rows(world.settings, _BRAND) if r[3] == muni]
        assert len(rows) == 1 and rows[0][6] == 1
    assert all(r[6] > 0 for r in reader_rows(world.settings, _BRAND))
    assert all(r[7] > 0 for r in reader_rows(world.settings, _LINE))


def test_classes_without_calibration_are_sin_calibracion(world):
    settings = world.settings
    cells = {r[4]: r[9] for r in reader_rows(settings, _CELL)}
    assert cells["CAMPERO"] == "no_calibration"  # regional rows, but no RUNT weight (D140)
    assert cells["GRUA"] == "no_calibration"  # no regional row at all
    assert cells["AUTOMOVIL"] == cells["CAMIONETA"] == "calibrated"
    brand_rows = [r for r in reader_rows(settings, _BRAND) if r[4] in ("CAMPERO", "GRUA")]
    assert {(r[4], r[5], r[6]) for r in brand_rows} == {
        ("CAMPERO", UNCAL, 40),
        ("GRUA", UNCAL, 7),
    }
    for r in brand_rows:  # no provenance, nothing was calibrated; quota = N
        assert r[7] == r[6] and r[8] is False
        assert r[9] is None and r[10] is None and r[11] is None and r[12] is None and r[13] is None
        assert r[14:17] == ("synthetic", "regional", "largest_remainder_v1")
    line_rows = [r for r in reader_rows(settings, _LINE) if r[4] in ("CAMPERO", "GRUA")]
    assert {(r[4], r[5], r[6], r[7]) for r in line_rows} == {
        ("CAMPERO", UNCAL, UNCAL, 40),
        ("GRUA", UNCAL, UNCAL, 7),
    }
    assert "assert_synthetic_uncalibrated_cells" in warns(world.output)
    # SIN CALIBRACION is not a regional brand: it only exists where the class has no share
    calibrated_classes = {r[4] for r in reader_rows(settings, _BRAND) if r[5] != UNCAL}
    assert not calibrated_classes & {"CAMPERO", "GRUA"}


def test_provenance_and_inherited_sample_size_flag(world):
    settings = world.settings
    sample = {(c, b): ok for c, b, _s, ok in reader_rows(settings, _SHARES)}
    for r in reader_rows(settings, _BRAND):
        assert r[14:17] == ("synthetic", "regional", "largest_remainder_v1")
        if r[5] == UNCAL:
            continue
        assert r[8] is sample[(r[4], r[5])]
        assert r[9] == f"{BOYACA},{RISARALDA}"
        assert (r[10], r[11]) == ("2026-07-06", "2026-07-06")
        assert (r[12], r[13]) == PUB  # the publication of the weights = the one of the cell
        assert (r[0], r[1]) == PUB
    line_sample = {(c, b, ln): ok for c, b, ln, _p, ok in reader_rows(settings, _LINE_SHARES)}
    for r in reader_rows(settings, _LINE):
        assert r[15:18] == ("synthetic", "regional", "largest_remainder_v1")
        if r[5] != UNCAL:
            assert r[9] is line_sample[(r[4], r[5], r[6])]
            assert (r[13], r[14]) == PUB
    # SIN ASIGNAR (D139) is a brand like any other and receives vehicles (D144 b)
    assert any(r[5] == "SIN ASIGNAR" and r[6] > 0 for r in reader_rows(settings, _BRAND))


def test_no_public_segment_and_the_drift_warn_fires_only_where_the_model_says(world):
    # the PUBLICO rows of the RUNT fixture (Tunja AUTOMOVIL 500, Medellin CAMPERO 10) are not here
    cells = {r[:5]: r[8] for r in reader_rows(world.settings, _CELL)}
    assert cells[(*PUB, "BOYACA", "TUNJA", "AUTOMOVIL")] == 3000
    assert cells[(*PUB, "ANTIOQUIA", "MEDELLIN", "CAMPERO")] == 40
    assert drifting(world.settings) == {"CAMIONETA"}  # 4 vehicles in 2 cells: ALFA 3/4 vs 0.5
    assert "assert_synthetic_brand_share_drift" in warns(world.output)


def test_a_second_build_and_the_synthetic_tag_alone_are_identical(world):
    before = snapshot(world.settings)
    assert all(before)
    code, output = world.run("build", select="tag:fleet_brand")
    assert code == 0, output
    assert snapshot(world.settings) == before
    # after A has run, the tag of the synthetic family builds on its own
    code, output = world.run("build", select="tag:brand_synthetic")
    assert code == 0, output
    assert re.search(r"OK created sql table model marts\.fct_synthetic_line_fleet", output)
    assert "fct_regional_brand_share" not in output  # family A was not rebuilt by the tag
    assert snapshot(world.settings) == before


@pytest.mark.parametrize("reverse_landing", [True])
def test_landing_in_another_order_gives_the_same_marts(world, warehouse, transform):
    assert bs.build_divipola(transform)[0] == 0
    code, output = transform("build", select="tag:fleet_brand")
    assert code == 0, output
    assert snapshot(warehouse[0]) == snapshot(world.settings)


# --- failure and recovery ---------------------------------------------------------------------


def test_fresh_database_fails_the_weight_node_and_skips_the_synthetic_marts(warehouse, transform):
    code, output = transform("build", select="tag:fleet_brand")
    assert code == 1
    assert re.search(r"ERROR creating sql table model marts\.fct_regional_brand_weight", output)
    for name in (
        "fct_synthetic_fleet_cell",
        "fct_synthetic_brand_fleet",
        "fct_synthetic_line_fleet",
    ):
        assert f"ERROR creating sql table model marts.{name}" not in output
        assert re.search(rf"SKIP relation marts\.{name}", output), name
    marts = {
        r[0]
        for r in warehouse[2].execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'marts'"
        )
    }
    assert not {m for m in marts if m.startswith("fct_synthetic")}
    # the synthetic tag alone, without A and without the demand mart, fails and builds nothing
    code, output = transform("build", select="tag:brand_synthetic")
    assert code == 1
    assert "ERROR" in output


@pytest.mark.parametrize("skew_cells", [100])
def test_a_skewed_fixture_warns_about_the_brand_share_drift(warehouse, transform):
    assert bs.build_divipola(transform)[0] == 0
    code, output = transform("build", select="tag:fleet_brand")
    assert code == 0, output  # a warn does not fail the build
    assert "assert_synthetic_brand_share_drift" in warns(output)
    assert "AUTOMOVIL" in drifting(
        warehouse[0]
    )  # the 100 one-vehicle cells all go to the top brand
    assert_matches_model(warehouse[0])  # the allocation itself is still exact


def test_forced_conservation_failure_exits_1_and_replay_recovers(world):
    good = snapshot(world.settings)
    try:
        # shares that no longer add up to 1: Hamilton cannot hand out the missing units
        world.admin.execute(
            "UPDATE marts.fct_regional_brand_share SET pooled_share = pooled_share * 0.9 "
            "WHERE vehicle_class_norm = 'AUTOMOVIL'"
        )
        code, output = world.run("build", select="tag:brand_synthetic")
        assert code == 1
        assert re.search(r"FAIL \d+ assert_synthetic_brand_conserves", output)
    finally:
        # replay after correcting the input: rebuilding family A restores the shares
        code, output = world.run("build", select="tag:fleet_brand")
    assert code == 0, output
    assert snapshot(world.settings) == good
    assert_matches_model(world.settings)

"""Synthetic seed + verification of the warehouse for the CI `pg` job (D113).

`seed` (loader profile) inserts one `ops.load_run` and 5 contiguous days of `landing.fx_rate`,
plus one `ops.load_run` and a few `landing.vehicle_fleet_snapshot` rows with hard names (accents,
enye, PUBLICO, INCONSISTENTE), plus one `ops.load_run` and a synthetic DIVIPOLA snapshot in
`landing.divipola_municipality` (D124: the 13 codes of the exception seed, the two municipalities
of the fleet rows and filler rows so the size guard passes), plus one `ops.load_run` and a
fictional regional snapshot per source in `landing.regional_fleet_brand_count` (D138: fictional
brands, so the fleet_brand marts of D140 have rows and a weight; the RUNT rows of departments
15 and 66 in FLEET are those weights). It refuses to run (exit 1) if landing
is not empty, so it can never mix synthetic rows with real ones. `verify` (reader profile) checks
that the marts built by dbt hold exactly what was seeded (exit 1 otherwise).
Settings come from the environment (D79); nothing sensitive is printed.
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import NoReturn

import psycopg
import typer

from pits.warehouse.connection import connect
from pits.warehouse.errors import WarehouseError, to_warehouse_error
from pits.warehouse.settings import Profile, WarehouseSettings, load_warehouse_settings

app = typer.Typer(add_completion=False, no_args_is_help=True, pretty_exceptions_show_locals=False)

FX_RATES = [Decimal(r) for r in ("4123.456789012345678", "4000.50", "3999.9900", "4010", "0.5")]
FX_DAYS = [date(2026, 1, 1) + timedelta(days=i) for i in range(len(FX_RATES))]
FLEET_PUBLICATION = (2026, 10)
# (department, municipality, service, status, class, registration_year, count)
FLEET = [
    ("NARIÑO", "PASTO", "PARTICULAR", "ACTIVO", "CAMIÓN", 2020, 5),
    ("NARINO", "PASTO", "PARTICULAR", "ACTIVO", "CAMION", 2020, 7),
    ("Nariño", "Pasto", "PÚBLICO", "ACTIVO", "camión  pesado", 2020, 11),
    ("NARIÑO", "PASTO", "PÚBLICO", "INCONSISTENTE", "CAMION PESADO", 2021, 13),
    ("BOGOTA, D.C.", "BOGOTA, D.C.", "OTROS", "ACTIVO", "ÑANDÚ ÜBER", 2018, 23),
    # D140: the RUNT weights of the two regional sources (departments 15 and 66).
    ("BOYACA", "TUNJA", "PARTICULAR", "ACTIVO", "AUTOMOVIL", 2020, 2000),
    ("RISARALDA", "PEREIRA", "PARTICULAR", "ACTIVO", "AUTOMOVIL", 2020, 1000),
]
# Distinct (department, municipality, class) _norm keys the dbt macro must produce from FLEET
# (D100: accents removed, upper case, collapsed spaces). Written by hand, NOT derived from FLEET.
FLEET_NORM_KEYS = [
    ("BOGOTA, D.C.", "BOGOTA, D.C.", "NANDU UBER"),
    ("BOYACA", "TUNJA", "AUTOMOVIL"),
    ("NARINO", "PASTO", "CAMION"),
    ("NARINO", "PASTO", "CAMION PESADO"),
    ("RISARALDA", "PEREIRA", "AUTOMOVIL"),
]
# D132/D134, written by hand from FLEET: the demand mart keeps the five ACTIVO PARTICULAR/PUBLICO
# rows as 4 cells (CAMIÓN and CAMION merge: 5 + 7 = 12, plus CAMION PESADO 11, TUNJA 2000 and
# PEREIRA 1000 = 3023 vehicles); the scope mart has 3 statuses (included 3023,
# excluded_status_inconsistente 13, excluded_service_otros 23 = 3059 vehicles, the FLEET total).
DEMAND_FLEET_EXPECTED = (4, 3023)
DEMAND_SCOPE_EXPECTED = (3, 3059)
# D138, fictional regional snapshots: (class, brand, line, service, status, count). Boyaca
# publishes service and status, Risaralda does not (NULL). AUTECO ACTIVE 110 resolves to SIN
# ASIGNAR through the real seed; SIN CLASE is out of the calibration (excluded_class).
REGIONAL = {
    "gobernacion_boyaca_parque_automotor": [
        ("AUTOMOVIL", "MARCA ALFA", "A1", "PARTICULAR", "ACTIVO", 60),
        ("AUTOMOVIL", "MARCA BETA", "B1", "PARTICULAR", "ACTIVO", 40),
        ("AUTOMOVIL", "AUTECO", "ACTIVE 110", "PARTICULAR", "ACTIVO", 3),
        ("AUTOMOVIL", "MARCA ALFA", "A1", "PUBLICO", "ACTIVO", 7),
    ],
    "gobernacion_risaralda_parque_automotor": [
        ("AUTOMOVIL", "MARCA ALFA", "A1", None, None, 30),
        ("AUTOMOVIL", "MARCA GAMMA", "G1", None, None, 70),
        ("SIN CLASE", "MARCA ZETA", "Z1", None, None, 2),
    ],
}
REGIONAL_ROWS_UPDATED = date(2026, 7, 6)
REGIONAL_HASHES = {
    "gobernacion_boyaca_parque_automotor": "d" * 64,
    "gobernacion_risaralda_parque_automotor": "e" * 64,
}
# Written by hand: weights AUTOMOVIL = {Boyaca 2000, Risaralda 1000} (the RUNT rows of FLEET); the
# calibration scope keeps 103 + 100 vehicles; the grids are 4 brands (or lines) x 2 regions.
WEIGHT_EXPECTED = (2, 3000)
SCOPE_REGIONAL_EXPECTED = (4, 212)  # (source, status) groups, all vehicles
BRAND_SHARE_EXPECTED = (8, 203)  # (rows, regional vehicles in scope)
LINE_SHARE_EXPECTED = (8, 203)
# p(MARCA ALFA | AUTOMOVIL) = (2000 * 60/103 + 1000 * 30/100) / 3000, from the numbers above.
ALFA_POOLED_SHARE = (Fraction(2000 * 60, 103) + Fraction(1000 * 30, 100)) / 3000
# D145, written by hand from FLEET and REGIONAL (not computed from them). The active PARTICULAR
# cells of the latest publication are PASTO CAMION (5 + 7 = 12), TUNJA AUTOMOVIL 2000 and PEREIRA
# AUTOMOVIL 1000 (PUBLICO, INCONSISTENTE and OTROS rows are out) = 3 cells, 3012 vehicles. Only
# AUTOMOVIL is calibrated (no regional source has CAMION; SIN CLASE has no share), so the single
# SIN CALIBRACION cell is PASTO CAMION (12). Pooled AUTOMOVIL shares (weights 2000/1000, scope
# Boyaca 60/40/3, Risaralda 30/70): ALFA .48835, BETA .25890, SIN ASIGNAR .01942, GAMMA .23333.
# Hamilton on TUNJA (N=2000): quotas 976.70/517.80/38.83/466.67 -> floors sum 1997, R=3 go to the
# largest remainders SIN ASIGNAR, BETA, ALFA = 977/518/39/466. On PEREIRA (N=1000): quotas
# 488.35/258.90/19.42/233.33 -> floors sum 998, R=2 go to BETA, SIN ASIGNAR = 488/259/20/233.
# Each brand has one line, so the line mart repeats the brand totals per department (Boyaca,
# Risaralda), plus the PASTO CAMION row: 4 + 4 + 1 = 9 rows in both marts.
SYNTHETIC_CELL_EXPECTED = (3, 3012)
SYNTHETIC_UNCALIBRATED_CELLS = [("PASTO", "CAMION", 12)]
SYNTHETIC_BRAND_EXPECTED = (9, 3012)
SYNTHETIC_LINE_EXPECTED = (9, 3012)
# (municipality_name_norm, vehicle_class_norm, brand_norm, synthetic_vehicle_count)
SYNTHETIC_BRAND_COUNTS = [
    ("PASTO", "CAMION", "SIN CALIBRACION", 12),
    ("PEREIRA", "AUTOMOVIL", "MARCA ALFA", 488),
    ("PEREIRA", "AUTOMOVIL", "SIN ASIGNAR", 20),
    ("TUNJA", "AUTOMOVIL", "MARCA ALFA", 977),
    ("TUNJA", "AUTOMOVIL", "MARCA BETA", 518),
    ("TUNJA", "AUTOMOVIL", "SIN ASIGNAR", 39),
]
FX_HASH = "a" * 64
FLEET_HASH = "b" * 64
DIVIPOLA_HASH = "c" * 64
DIVIPOLA_UPDATED = date(2025, 1, 24)
# (department_code, department_name, municipality_code, municipality_name, type, longitude,
# latitude) as DIVIPOLA publishes them (accents, decimal comma). The 13 codes of the exception seed
# (transform/seeds, D126) must exist, with their DANE names; PASTO and BOGOTA, D.C. match FLEET by
# normalized name. Written by hand: this is test data, not a copy of the real table.
DIVIPOLA_NAMED = [
    ("05", "ANTIOQUIA", "05042", "SANTA FÉ DE ANTIOQUIA", "Municipio", "-75,8", "6,55"),
    ("05", "ANTIOQUIA", "05237", "DONMATÍAS", "Municipio", "-75,4", "6,48"),
    ("11", "BOGOTÁ, D.C.", "11001", "BOGOTÁ, D.C.", "Municipio", "-74,106992", "4,649251"),
    ("13", "BOLÍVAR", "13001", "CARTAGENA DE INDIAS", "Municipio", "-75,5", "10,4"),
    ("13", "BOLÍVAR", "13468", "SANTA CRUZ DE MOMPOX", "Municipio", "-74,4", "9,2"),
    ("15", "BOYACÁ", "15001", "TUNJA", "Municipio", "-73,36", "5,53"),
    ("19", "CAUCA", "19548", "PIENDAMÓ - TUNÍA", "Municipio", "-76,5", "2,6"),
    ("25", "CUNDINAMARCA", "25843", "VILLA DE SAN DIEGO DE UBATÉ", "Municipio", "-73,8", "5,3"),
    ("52", "NARIÑO", "52001", "PASTO", "Municipio", "-77,28", "1,21"),
    ("52", "NARIÑO", "52835", "SAN ANDRÉS DE TUMACO", "Municipio", "-78,8", "1,8"),
    ("54", "NORTE DE SANTANDER", "54001", "SAN JOSÉ DE CÚCUTA", "Municipio", "-72,5", "7,9"),
    ("70", "SUCRE", "70742", "SAN LUIS DE SINCÉ", "Municipio", "-75,1", "9,2"),
    ("66", "RISARALDA", "66001", "PEREIRA", "Municipio", "-75,69", "4,81"),
    ("73", "TOLIMA", "73443", "SAN SEBASTIÁN DE MARIQUITA", "Municipio", "-74,9", "5,2"),
    ("76", "VALLE DEL CAUCA", "76001", "SANTIAGO DE CALI", "Municipio", "-76,5", "3,4"),
    (
        "88",
        "ARCHIPIÉLAGO DE SAN ANDRÉS, PROVIDENCIA Y SANTA CATALINA",
        "88001",
        "SAN ANDRÉS",
        "Isla",
        "-81,707181",
        "12,578108",
    ),
]
# Filler so the size guard of D125 (>= 1,100 rows) passes: departments 30..39, 110 each.
DIVIPOLA_FILLER = [
    (f"{d:02d}", f"DEPARTAMENTO {d}", f"{d:02d}{m:03d}", f"MUNICIPIO {d} {m}", "Municipio",
     "-74,5", "5,5")
    for d in range(30, 40)
    for m in range(1, 111)
]  # fmt: skip
DIVIPOLA = [*DIVIPOLA_NAMED, *DIVIPOLA_FILLER]
# (department_norm, municipality_norm, code, method) the map must give for the FLEET pairs.
FLEET_DANE_KEYS = [
    ("BOGOTA, D.C.", "BOGOTA, D.C.", "11001", "auto_norm"),
    ("BOYACA", "TUNJA", "15001", "auto_norm"),
    ("NARINO", "PASTO", "52001", "auto_norm"),
    ("RISARALDA", "PEREIRA", "66001", "auto_norm"),
]

_LOAD_RUN_SQL = (
    "INSERT INTO ops.load_run (dataset, source_system, input_fingerprint, transform_name, "
    "rules_version, manifest_key, manifest_sha256, csv_key, csv_sha256, csv_size_bytes, "
    "row_count, coverage_from, coverage_to, last_input_batch_id, last_input_extraction_date, "
    "last_input_finished_at, normalized_manifest, loader_version) VALUES "
    "(%s, %s, %s, 'synthetic', '1', 'synthetic/ci', %s, 'synthetic/ci.csv', %s, 1, %s, %s, %s, "
    "%s, %s, now(), '{}'::jsonb, 'ci') RETURNING load_id"
)
_FX_SQL = (
    "INSERT INTO landing.fx_rate (rate_date, currency_from, currency_to, rate, source_system, "
    "source_reference, load_id) VALUES (%s, 'USD', 'COP', %s, 'superfinanciera_trm', %s, %s)"
)
_FLEET_SQL = (
    "INSERT INTO landing.vehicle_fleet_snapshot (publication_year, publication_month, "
    "department_name, municipality_name, service_name, vehicle_status, vehicle_class, "
    "registration_year, vehicle_count, source_system, source_reference, load_id) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'mintransporte_runt_parque', %s, %s)"
)
_REGIONAL_SQL = (
    "INSERT INTO landing.regional_fleet_brand_count (source_system, rows_updated, vehicle_class, "
    "brand, line, service_name, vehicle_status, vehicle_count, source_reference, load_id) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_DIVIPOLA_SQL = (
    "INSERT INTO landing.divipola_municipality (department_code, department_name, "
    "municipality_code, municipality_name, municipality_type, longitude, latitude, "
    "source_system, source_reference, load_id) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, 'dane_divipola', %s, %s)"
)


def _settings(profile: Profile) -> WarehouseSettings:
    return load_warehouse_settings(os.environ, (profile,))


# Replaceable in tests (they inject the per-test database settings).
settings_factory: Callable[[Profile], WarehouseSettings] = _settings


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


def _load_run(
    conn: psycopg.Connection,
    dataset: str,
    source: str,
    digest: str,
    rows: int,
    start: date,
    end: date,
) -> int:
    row = conn.execute(
        _LOAD_RUN_SQL,
        (dataset, source, digest, digest, digest, rows, start, end, str(uuid.uuid4()), end),
    ).fetchone()
    return row[0]


def seed(settings: WarehouseSettings) -> bool:
    """Insert the seed in ONE transaction; False (nothing written) if landing is not empty."""
    failure: WarehouseError | None = None
    try:
        return _seed(settings)
    except psycopg.Error as exc:
        failure = to_warehouse_error(exc, "seed")
    raise failure  # outside the except block: no __context__ holding the connection


def _seed(settings: WarehouseSettings) -> bool:
    conn = connect(settings, Profile.LOADER)
    try:
        for table in (
            "landing.fx_rate",
            "landing.vehicle_fleet_snapshot",
            "landing.divipola_municipality",
            "landing.regional_fleet_brand_count",
        ):
            if conn.execute(f"SELECT EXISTS (SELECT 1 FROM {table})").fetchone()[0]:
                return False
        fx_id = _load_run(
            conn, "fx_rate", "superfinanciera_trm", FX_HASH, len(FX_DAYS), FX_DAYS[0], FX_DAYS[-1]
        )
        for n, (day, rate) in enumerate(zip(FX_DAYS, FX_RATES, strict=True)):
            conn.execute(_FX_SQL, (day, rate, f"synthetic/ci#{n}", fx_id))
        publication = date(*FLEET_PUBLICATION, 1)
        fleet_id = _load_run(
            conn,
            "vehicle_fleet_snapshot",
            "mintransporte_runt_parque",
            FLEET_HASH,
            len(FLEET),
            publication,
            publication,
        )
        for n, row in enumerate(FLEET):
            conn.execute(_FLEET_SQL, (*FLEET_PUBLICATION, *row, f"synthetic/ci#{n}", fleet_id))
        divipola_id = _load_run(
            conn,
            "divipola_municipality",
            "dane_divipola",
            DIVIPOLA_HASH,
            len(DIVIPOLA),
            DIVIPOLA_UPDATED,
            DIVIPOLA_UPDATED,
        )
        for n, row in enumerate(DIVIPOLA):
            conn.execute(_DIVIPOLA_SQL, (*row, f"synthetic/ci#{n}", divipola_id))
        for source_system, rows in REGIONAL.items():
            regional_id = _load_run(
                conn,
                "regional_fleet_brand_count",
                source_system,
                REGIONAL_HASHES[source_system],
                len(rows),
                REGIONAL_ROWS_UPDATED,
                REGIONAL_ROWS_UPDATED,
            )
            for n, (cls, brand, line, service, status, count) in enumerate(rows):
                conn.execute(
                    _REGIONAL_SQL,
                    (
                        source_system, REGIONAL_ROWS_UPDATED, cls, brand, line, service, status,
                        count, f"synthetic/ci#{n}", regional_id,
                    ),
                )  # fmt: skip
        conn.commit()
        return True
    finally:
        conn.close()


def verify(settings: WarehouseSettings) -> list[str]:
    """Return the mismatches between the marts and the seed (empty = ok)."""
    failure: WarehouseError | None = None
    try:
        return _verify(settings)
    except psycopg.Error as exc:
        failure = to_warehouse_error(exc, "verify")
    raise failure  # outside the except block: no __context__ holding the connection


def _verify(settings: WarehouseSettings) -> list[str]:
    conn = connect(settings, Profile.READER, autocommit=True)
    try:
        fx = conn.execute("SELECT count(*), sum(rate) FROM marts.fct_fx_rate_daily").fetchone()
        fleet = conn.execute(
            "SELECT count(*), sum(vehicle_count) FROM marts.fct_vehicle_fleet_snapshot"
        ).fetchone()
        keys = conn.execute(
            "SELECT DISTINCT department_name_norm, municipality_name_norm, vehicle_class_norm "
            "FROM marts.fct_vehicle_fleet_snapshot ORDER BY 1, 2, 3"
        ).fetchall()
        dim = conn.execute("SELECT count(*) FROM marts.dim_municipality").fetchone()
        dane = conn.execute(
            "SELECT count(*), sum(vehicle_count), count(dane_municipality_code) "
            "FROM marts.fct_vehicle_fleet_snapshot_dane"
        ).fetchone()
        dane_keys = conn.execute(
            "SELECT DISTINCT department_name_norm, municipality_name_norm, "
            "dane_municipality_code, dane_match_method "
            "FROM marts.fct_vehicle_fleet_snapshot_dane ORDER BY 1, 2"
        ).fetchall()
        demand = conn.execute(
            "SELECT count(*), sum(active_vehicle_count) FROM marts.fct_parts_demand_fleet"
        ).fetchone()
        scope = conn.execute(
            "SELECT count(*), sum(vehicle_count) FROM marts.fct_parts_demand_scope"
        ).fetchone()
        weight = conn.execute(
            "SELECT count(*), sum(weight_vehicle_count) FROM marts.fct_regional_brand_weight"
        ).fetchone()
        regional_scope = conn.execute(
            "SELECT count(*), sum(vehicle_count) FROM marts.fct_regional_fleet_brand_scope"
        ).fetchone()
        brand_share = conn.execute(
            "SELECT count(*), sum(vehicle_count) FROM marts.fct_regional_brand_share"
        ).fetchone()
        line_share = conn.execute(
            "SELECT count(*), sum(vehicle_count) FROM marts.fct_regional_line_share"
        ).fetchone()
        alfa = conn.execute(
            "SELECT DISTINCT pooled_share FROM marts.fct_regional_brand_share "
            "WHERE vehicle_class_norm = 'AUTOMOVIL' AND brand_norm = 'MARCA ALFA'"
        ).fetchall()
        sin_asignar = conn.execute(
            "SELECT count(*) FROM marts.fct_regional_brand_share WHERE brand_norm = 'SIN ASIGNAR'"
        ).fetchone()
        syn_cell = conn.execute(
            "SELECT count(*), sum(active_vehicle_count) FROM marts.fct_synthetic_fleet_cell"
        ).fetchone()
        syn_uncal = conn.execute(
            "SELECT municipality_name_norm, vehicle_class_norm, active_vehicle_count "
            "FROM marts.fct_synthetic_fleet_cell WHERE calibration_status = 'no_calibration' "
            "ORDER BY 1, 2"
        ).fetchall()
        syn_brand = conn.execute(
            "SELECT count(*), sum(synthetic_vehicle_count) FROM marts.fct_synthetic_brand_fleet"
        ).fetchone()
        syn_line = conn.execute(
            "SELECT count(*), sum(synthetic_vehicle_count) FROM marts.fct_synthetic_line_fleet"
        ).fetchone()
        syn_counts = conn.execute(
            "SELECT municipality_name_norm, vehicle_class_norm, brand_norm, "
            "synthetic_vehicle_count "
            "FROM marts.fct_synthetic_brand_fleet WHERE (municipality_name_norm, brand_norm) IN "
            "(('PASTO', 'SIN CALIBRACION'), ('PEREIRA', 'MARCA ALFA'), ('PEREIRA', 'SIN ASIGNAR'), "
            "('TUNJA', 'MARCA ALFA'), ('TUNJA', 'MARCA BETA'), ('TUNJA', 'SIN ASIGNAR')) "
            "ORDER BY 1, 2, 3"
        ).fetchall()
        syn_active = conn.execute(
            "SELECT sum(active_vehicle_count) FROM marts.fct_parts_demand_fleet "
            "WHERE demand_segment = 'particular' AND publication_year * 100 + publication_month = "
            "(SELECT max(publication_year * 100 + publication_month) "
            "FROM marts.fct_parts_demand_fleet)"
        ).fetchone()
    finally:
        conn.close()
    expected = {
        "fct_fx_rate_daily": ((len(FX_DAYS), sum(FX_RATES)), fx),
        "fct_vehicle_fleet_snapshot": ((len(FLEET), sum(r[-1] for r in FLEET)), fleet),
        "dim_municipality": ((len(DIVIPOLA),), dim),
        # D127: same rows as the fct, and every cell of the seed finds its DANE code.
        "fct_vehicle_fleet_snapshot_dane": (
            (len(FLEET), sum(r[-1] for r in FLEET), len(FLEET)),
            dane,
        ),
        "fct_parts_demand_fleet": (DEMAND_FLEET_EXPECTED, demand),
        "fct_parts_demand_scope": (DEMAND_SCOPE_EXPECTED, scope),
        "fct_regional_brand_weight": (WEIGHT_EXPECTED, weight),
        "fct_regional_fleet_brand_scope": (SCOPE_REGIONAL_EXPECTED, regional_scope),
        "fct_regional_brand_share": (BRAND_SHARE_EXPECTED, brand_share),
        "fct_regional_line_share": (LINE_SHARE_EXPECTED, line_share),
        "fct_synthetic_fleet_cell": (SYNTHETIC_CELL_EXPECTED, syn_cell),
        "fct_synthetic_brand_fleet": (SYNTHETIC_BRAND_EXPECTED, syn_brand),
        "fct_synthetic_line_fleet": (SYNTHETIC_LINE_EXPECTED, syn_line),
    }
    problems = [
        f"{name}: expected (rows, total)={want}, got {tuple(got)}"
        for name, (want, got) in expected.items()
        if tuple(got) != want
    ]
    if [tuple(k) for k in keys] != sorted(FLEET_NORM_KEYS):
        problems.append(f"fct_vehicle_fleet_snapshot: normalized keys {keys} != {FLEET_NORM_KEYS}")
    if [tuple(k) for k in dane_keys] != sorted(FLEET_DANE_KEYS):
        problems.append(
            f"fct_vehicle_fleet_snapshot_dane: DANE codes {dane_keys} != {FLEET_DANE_KEYS}"
        )
    # D140: one pooled value per (class, brand), equal to the hand-computed weighted share; the
    # AUTECO line of the seed shows up as SIN ASIGNAR once per region of the class (2 rows).
    if len(alfa) != 1 or alfa[0][0] is None or abs(Fraction(alfa[0][0]) - ALFA_POOLED_SHARE) > 1e-9:
        problems.append(
            f"fct_regional_brand_share: pooled MARCA ALFA {alfa} != {ALFA_POOLED_SHARE}"
        )
    if tuple(sin_asignar) != (2,):
        problems.append(f"fct_regional_brand_share: SIN ASIGNAR rows {sin_asignar} != (2,)")
    # D145: conservation (sum synthetic = sum active PARTICULAR of the latest publication), the
    # uncalibrated cells and a few hand-computed brand counts.
    if syn_brand[1] != syn_active[0] or syn_line[1] != syn_active[0]:
        problems.append(
            f"synthetic marts: brand {syn_brand[1]} / line {syn_line[1]} != active PARTICULAR "
            f"{syn_active[0]}"
        )
    if [tuple(r) for r in syn_uncal] != SYNTHETIC_UNCALIBRATED_CELLS:
        problems.append(
            f"fct_synthetic_fleet_cell: no_calibration cells {syn_uncal} != "
            f"{SYNTHETIC_UNCALIBRATED_CELLS}"
        )
    if [tuple(r) for r in syn_counts] != sorted(SYNTHETIC_BRAND_COUNTS):
        problems.append(
            f"fct_synthetic_brand_fleet: brand counts {syn_counts} != {SYNTHETIC_BRAND_COUNTS}"
        )
    return problems


@app.command("seed")
def seed_command() -> None:
    """Insert the synthetic landing data as the loader (exit 1 if landing is not empty)."""
    try:
        done = seed(settings_factory(Profile.LOADER))
    except WarehouseError as exc:
        _fail(str(exc))
    if not done:
        _fail("landing is not empty; refusing to seed")
    typer.echo(
        f"seeded fx_rate={len(FX_DAYS)} vehicle_fleet_snapshot={len(FLEET)} "
        f"divipola_municipality={len(DIVIPOLA)} "
        f"regional_fleet_brand_count={sum(len(r) for r in REGIONAL.values())}"
    )


@app.command("verify")
def verify_command() -> None:
    """Check the marts against the seed as the reader (exit 1 on any mismatch)."""
    try:
        problems = verify(settings_factory(Profile.READER))
    except WarehouseError as exc:
        _fail(str(exc))
    if problems:
        _fail("; ".join(problems))
    typer.echo("verified marts match the seed")


if __name__ == "__main__":
    sys.exit(app())

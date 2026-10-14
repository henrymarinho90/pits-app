"""Synthetic seed + verification of the warehouse for the CI `pg` job (D113).

`seed` (loader profile) inserts one `ops.load_run` and 5 contiguous days of `landing.fx_rate`,
plus one `ops.load_run` and a few `landing.vehicle_fleet_snapshot` rows with hard names (accents,
enye, PUBLICO, INCONSISTENTE), plus one `ops.load_run` and a synthetic DIVIPOLA snapshot in
`landing.divipola_municipality` (D124: the 13 codes of the exception seed, the two municipalities
of the fleet rows and filler rows so the size guard passes). It refuses to run (exit 1) if landing
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
]
# Distinct (department, municipality, class) _norm keys the dbt macro must produce from FLEET
# (D100: accents removed, upper case, collapsed spaces). Written by hand, NOT derived from FLEET.
FLEET_NORM_KEYS = [
    ("BOGOTA, D.C.", "BOGOTA, D.C.", "NANDU UBER"),
    ("NARINO", "PASTO", "CAMION"),
    ("NARINO", "PASTO", "CAMION PESADO"),
]
# D132/D134, written by hand from FLEET: the demand mart keeps the three ACTIVO PARTICULAR/PUBLICO
# rows as 2 cells (CAMIÓN and CAMION merge: 5 + 7 = 12, plus CAMION PESADO 11 = 23 vehicles); the
# scope mart has 3 statuses (included 23, excluded_status_inconsistente 13, excluded_service_otros
# 23 = 59 vehicles, the FLEET total).
DEMAND_FLEET_EXPECTED = (2, 23)
DEMAND_SCOPE_EXPECTED = (3, 59)
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
    ("19", "CAUCA", "19548", "PIENDAMÓ - TUNÍA", "Municipio", "-76,5", "2,6"),
    ("25", "CUNDINAMARCA", "25843", "VILLA DE SAN DIEGO DE UBATÉ", "Municipio", "-73,8", "5,3"),
    ("52", "NARIÑO", "52001", "PASTO", "Municipio", "-77,28", "1,21"),
    ("52", "NARIÑO", "52835", "SAN ANDRÉS DE TUMACO", "Municipio", "-78,8", "1,8"),
    ("54", "NORTE DE SANTANDER", "54001", "SAN JOSÉ DE CÚCUTA", "Municipio", "-72,5", "7,9"),
    ("70", "SUCRE", "70742", "SAN LUIS DE SINCÉ", "Municipio", "-75,1", "9,2"),
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
    ("NARINO", "PASTO", "52001", "auto_norm"),
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
        f"divipola_municipality={len(DIVIPOLA)}"
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

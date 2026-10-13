"""Synthetic seed + verification of the warehouse for the CI `pg` job (D113).

`seed` (loader profile) inserts one `ops.load_run` and 5 contiguous days of `landing.fx_rate`,
plus one `ops.load_run` and a few `landing.vehicle_fleet_snapshot` rows with hard names (accents,
enye, PUBLICO, INCONSISTENTE). It refuses to run (exit 1) if landing is not empty, so it can never
mix synthetic rows with real ones. `verify` (reader profile) checks that the marts built by dbt
hold exactly what was seeded (exit 1 otherwise).
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

import typer

from pits.warehouse.connection import connect
from pits.warehouse.errors import WarehouseError
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
FX_HASH = "a" * 64
FLEET_HASH = "b" * 64

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


def _settings(profile: Profile) -> WarehouseSettings:
    return load_warehouse_settings(os.environ, (profile,))


# Replaceable in tests (they inject the per-test database settings).
settings_factory: Callable[[Profile], WarehouseSettings] = _settings


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


def _load_run(conn, dataset, source, digest, rows, start, end) -> int:
    row = conn.execute(
        _LOAD_RUN_SQL,
        (dataset, source, digest, digest, digest, rows, start, end, str(uuid.uuid4()), end),
    ).fetchone()
    return row[0]


def seed(settings: WarehouseSettings) -> bool:
    """Insert the seed in ONE transaction; False (nothing written) if landing is not empty."""
    conn = connect(settings, Profile.LOADER)
    try:
        for table in ("landing.fx_rate", "landing.vehicle_fleet_snapshot"):
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
        conn.commit()
        return True
    finally:
        conn.close()


def verify(settings: WarehouseSettings) -> list[str]:
    """Return the mismatches between the marts and the seed (empty = ok)."""
    conn = connect(settings, Profile.READER, autocommit=True)
    try:
        fx = conn.execute("SELECT count(*), sum(rate) FROM marts.fct_fx_rate_daily").fetchone()
        fleet = conn.execute(
            "SELECT count(*), sum(vehicle_count) FROM marts.fct_vehicle_fleet_snapshot"
        ).fetchone()
    finally:
        conn.close()
    expected = {
        "fct_fx_rate_daily": ((len(FX_DAYS), sum(FX_RATES)), fx),
        "fct_vehicle_fleet_snapshot": ((len(FLEET), sum(r[-1] for r in FLEET)), fleet),
    }
    return [
        f"{name}: expected (rows, total)={want}, got {tuple(got)}"
        for name, (want, got) in expected.items()
        if tuple(got) != want
    ]


@app.command("seed")
def seed_command() -> None:
    """Insert the synthetic landing data as the loader (exit 1 if landing is not empty)."""
    try:
        done = seed(settings_factory(Profile.LOADER))
    except WarehouseError as exc:
        _fail(str(exc))
    if not done:
        _fail("landing is not empty; refusing to seed")
    typer.echo(f"seeded fx_rate={len(FX_DAYS)} vehicle_fleet_snapshot={len(FLEET)}")


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

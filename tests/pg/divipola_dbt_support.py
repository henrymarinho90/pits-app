"""Shared fixtures for the DIVIPOLA dbt tests against a per-test database (not a test module).

`warehouse` migrates a fresh database and loads a synthetic DIVIPOLA snapshot into landing (the
real 13 municipalities the RUNT cannot match by name plus filler rows to pass the size guard);
`transform` runs the real `pits transform` CLI and the real dbt subprocess against it, on a copy
of the dbt project in tmp_path (so target/ and logs/ never touch the checkout).
"""

from __future__ import annotations

import shutil
import uuid

import pytest
from typer.testing import CliRunner

from pits.cli import app
from pits.transform import cli as tcli
from pits.transform import runner as rn
from pits.warehouse.connection import connect
from pits.warehouse.migrate import run_migrate
from pits.warehouse.settings import Profile

runner = CliRunner()
HASH = "d" * 64

# (department_code, department_name, municipality_code, municipality_name, type, lon, lat)
REAL = [
    ("05", "ANTIOQUIA", "05001", "MEDELLÍN", "Municipio", "-75,581775", "6,246631"),
    ("05", "ANTIOQUIA", "05042", "SANTA FÉ DE ANTIOQUIA", "Municipio", "-75,8", "6,55"),
    ("05", "ANTIOQUIA", "05237", "DONMATÍAS", "Municipio", "-75,4", "6,48"),
    ("11", "BOGOTÁ, D.C.", "11001", "BOGOTÁ, D.C.", "Municipio", "-74,106992", "4,649251"),
    ("13", "BOLÍVAR", "13001", "CARTAGENA DE INDIAS", "Municipio", "-75,5", "10,4"),
    ("13", "BOLÍVAR", "13468", "SANTA CRUZ DE MOMPOX", "Municipio", "-74,4", "9,2"),
    ("13", "BOLÍVAR", "13683", "SANTA ROSA", "Municipio", "-74,5", "10,4"),
    ("13", "BOLÍVAR", "13688", "SANTA ROSA DEL SUR", "Municipio", "-74,0", "7,9"),
    ("19", "CAUCA", "19548", "PIENDAMÓ - TUNÍA", "Municipio", "-76,5", "2,6"),
    ("19", "CAUCA", "19701", "SANTA ROSA", "Municipio", "-76,7", "1,7"),
    ("25", "CUNDINAMARCA", "25843", "VILLA DE SAN DIEGO DE UBATÉ", "Municipio", "-73,8", "5,3"),
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
    ("91", "AMAZONAS", "91263", "EL ENCANTO", "Área no municipalizada", "-73,2", "-1,7"),
]
FILLER_DEPARTMENTS = range(30, 40)  # codes 30..39, 110 municipalities each = 1,100 rows


def divipola_rows() -> list[tuple[str, ...]]:
    filler = [
        (f"{d:02d}", f"DEPARTAMENTO {d}", f"{d:02d}{m:03d}", f"MUNICIPIO {d} {m}", "Municipio",
         "-74,5", "5,5")
        for d in FILLER_DEPARTMENTS
        for m in range(1, 111)
    ]  # fmt: skip
    return [*REAL, *filler]


_LOAD_RUN_SQL = (
    "INSERT INTO ops.load_run (dataset, source_system, input_fingerprint, transform_name, "
    "rules_version, manifest_key, manifest_sha256, csv_key, csv_sha256, csv_size_bytes, "
    "row_count, coverage_from, coverage_to, last_input_batch_id, last_input_extraction_date, "
    "last_input_finished_at, normalized_manifest, loader_version) VALUES "
    "('divipola_municipality', 'dane_divipola', %s, 't', '1', 'k', %s, 'c', %s, 1, %s, "
    "'2025-01-24', '2025-01-24', %s, '2026-10-13', now(), '{}'::jsonb, '0.1') RETURNING load_id"
)
_LANDING_SQL = (
    "INSERT INTO landing.divipola_municipality VALUES (%s, %s, %s, %s, %s, %s, %s, "
    "'dane_divipola', %s, %s)"
)


def load_divipola_landing(loader, rows) -> int:
    load_id = loader.execute(
        _LOAD_RUN_SQL, (HASH, HASH, HASH, len(rows), str(uuid.uuid4()))
    ).fetchone()[0]
    for i, row in enumerate(rows):
        loader.execute(_LANDING_SQL, (*row, f"raw/divipola#{i}", load_id))
    return load_id


@pytest.fixture
def warehouse(pg_settings):
    """Migrated database with the synthetic snapshot in landing: (settings, loader, admin)."""
    run_migrate(pg_settings)
    loader = connect(pg_settings, Profile.LOADER, autocommit=True)
    admin = connect(pg_settings, Profile.ADMIN, autocommit=True)
    load_divipola_landing(loader, divipola_rows())
    yield pg_settings, loader, admin
    loader.close()
    admin.close()


@pytest.fixture
def transform(warehouse, monkeypatch, tmp_path, capfd):
    """Run `pits transform <command>` with the test settings; returns (exit_code, output)."""
    settings = warehouse[0]
    project = tmp_path / "transform"
    shutil.copytree(
        rn.default_project_dir(),
        project,
        ignore=shutil.ignore_patterns("target", "logs", "dbt_packages"),
    )
    monkeypatch.setattr(tcli, "project_dir_factory", lambda: project)
    monkeypatch.setattr(tcli, "settings_factory", lambda env: settings)

    def run(command, select=None):
        capfd.readouterr()  # drop output of earlier invocations
        args = ["transform", command, *(["--select", select] if select else [])]
        result = runner.invoke(app, args)
        captured = capfd.readouterr()
        return result.exit_code, result.output + captured.out + captured.err

    run.project = project
    return run


def reader_rows(settings, sql, params=()):
    """Rows seen by the BI reader role (marts only)."""
    reader = connect(settings, Profile.READER, autocommit=True)
    try:
        return reader.execute(sql, params).fetchall()
    finally:
        reader.close()


# --- RUNT vehicle fleet (one publication, 2026-10) ----------------------------------------------

FLEET_HASH = "e" * 64
# (department, municipality, service, status, class, registration_year, count) as the RUNT writes
# them (no accents, truncated department names). Pairs: auto match, curated exceptions, homonyms
# (SANTA ROSA in two departments), a leading-zero code (DON MATIAS) and an unmatched small pair.
FLEET = [
    ("ANTIOQUIA", "MEDELLIN", "PARTICULAR", "ACTIVO", "AUTOMOVIL", 2020, 1000),
    ("BOGOTA D.C.", "BOGOTA", "PARTICULAR", "ACTIVO", "AUTOMOVIL", 2020, 5000),
    ("BOGOTA D.C.", "BOGOTA", "PÚBLICO", "INCONSISTENTE", "BUS", 2015, 40),
    ("VALLE DEL CAUCA", "CALI", "PARTICULAR", "ACTIVO", "MOTOCICLETA", 2022, 3000),
    ("BOLIVAR", "SANTA ROSA", "PARTICULAR", "ACTIVO", "CAMPERO", 2010, 100),
    ("CAUCA", "SANTA ROSA", "PARTICULAR", "ACTIVO", "CAMPERO", 2010, 50),
    ("ANTIOQUIA", "DON MATIAS", "PARTICULAR", "ACTIVO", "AUTOMOVIL", 2019, 20),
    ("TOLIMA", "PUEBLITO", "PARTICULAR", "ACTIVO", "AUTOMOVIL", 2019, 5),
]
_FLEET_RUN_SQL = (
    "INSERT INTO ops.load_run (dataset, source_system, input_fingerprint, transform_name, "
    "rules_version, manifest_key, manifest_sha256, csv_key, csv_sha256, csv_size_bytes, "
    "row_count, coverage_from, coverage_to, last_input_batch_id, last_input_extraction_date, "
    "last_input_finished_at, normalized_manifest, loader_version) VALUES "
    "('vehicle_fleet_snapshot', 'mintransporte_runt_parque', %s, 't', '1', 'k', %s, 'c', %s, 1, "
    "%s, '2026-10-01', '2026-10-01', %s, '2026-10-12', now(), '{}'::jsonb, '0.1') RETURNING load_id"
)
_FLEET_SQL = (
    "INSERT INTO landing.vehicle_fleet_snapshot VALUES (2026, 10, %s, %s, %s, %s, %s, %s, %s, "
    "'mintransporte_runt_parque', %s, %s)"
)


def load_fleet_landing(loader, rows) -> int:
    load_id = loader.execute(
        _FLEET_RUN_SQL, (FLEET_HASH, FLEET_HASH, FLEET_HASH, len(rows), str(uuid.uuid4()))
    ).fetchone()[0]
    for i, row in enumerate(rows):
        loader.execute(_FLEET_SQL, (*row, f"raw/fleet#{i}", load_id))
    return load_id


@pytest.fixture
def fleet(warehouse):
    """The DIVIPOLA warehouse plus one RUNT publication: (settings, loader, admin)."""
    load_fleet_landing(warehouse[1], FLEET)
    return warehouse


def build_divipola(transform):
    """The documented bootstrap order: the RUNT build first (its fct does not need DIVIPOLA; the
    DANE nodes fail without the dimension), then the DIVIPOLA build that creates the dimension and
    everything that depends on it. Returns the result of the second one."""
    code, output = transform("build", select="tag:vehicle_fleet")
    assert code == 1 and "fct_vehicle_fleet_snapshot" in output, output
    return transform("build", select="tag:divipola")

"""`pits transform` end to end against a per-test database (D85-D88, D87 tests of the project).

The real CLI and the real dbt subprocess run; only the settings (test database, suffixed
transformer role, in-memory password) and the project directory are injected. The dbt project
is COPIED to tmp_path per test, so target/ and logs/ never touch the repository checkout.
"""

from __future__ import annotations

import dataclasses
import re
import shutil
import uuid

import pytest
from psycopg import errors as pgerr
from typer.testing import CliRunner

from pits.cli import app
from pits.transform import cli as tcli
from pits.transform import runner as rn
from pits.warehouse.connection import connect
from pits.warehouse.migrate import run_migrate
from pits.warehouse.settings import Profile

runner = CliRunner()
HASH = "a" * 64
RATES = ["4123.456789012345678", "4000.50", "3999.9900", "4010", "0.0000001"]
DAYS = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]

_LOAD_RUN_SQL = (
    "INSERT INTO ops.load_run (dataset, source_system, input_fingerprint, transform_name, "
    "rules_version, manifest_key, manifest_sha256, csv_key, csv_sha256, csv_size_bytes, "
    "row_count, coverage_from, coverage_to, last_input_batch_id, last_input_extraction_date, "
    "last_input_finished_at, normalized_manifest, loader_version) VALUES "
    "('fx_rate', 'superfinanciera_trm', %s, 't', '1', 'k', %s, 'c', %s, 1, 1, "
    "'2026-01-01', '2026-01-05', %s, '2026-01-05', now(), '{}'::jsonb, '0.1') RETURNING load_id"
)
_FLEET_RUN_SQL = _LOAD_RUN_SQL.replace(
    "('fx_rate', 'superfinanciera_trm', %s, 't', '1', 'k', %s, 'c', %s, 1, 1, "
    "'2026-01-01', '2026-01-05',",
    "('vehicle_fleet_snapshot', 'mintransporte_runt_parque', %s, 't', '1', 'k', %s, 'c', %s, 1, "
    "%s, '2026-10-01', '2026-10-01',",
)
FLEET_HASH = "b" * 64
# (department, municipality, service, status, class, registration_year, count): spellings that
# must unify after normalization (accents, case, repeated spaces) plus ones that must not.
FLEET = [
    ("NARIÑO", "PASTO", "PARTICULAR", "ACTIVO", "CAMIÓN", 2020, 5),
    ("NARINO", "PASTO", "PARTICULAR", "ACTIVO", "CAMION", 2020, 7),
    ("Nariño", "Pasto", "PÚBLICO", "ACTIVO", "camión  pesado", 2020, 11),
    ("NARIÑO", "PASTO", "PÚBLICO", "INCONSISTENTE", "CAMION PESADO", 2021, 13),
    (
        "ARCHIPIELAGO DE SAN ANDRES, PROVIDENCIA",
        "SAN ANDRES",
        "OFICIAL",
        "ACTIVO",
        "MOTOCICLETA",
        2019,
        17,
    ),
    ("BOGOTA, D.C.", "BOGOTA, D.C.", "NO REGISTRA", "ACTIVO", "AUTOMÓVIL (4X4)", 2018, 19),
    ("BOGOTA, D.C.", "BOGOTA, D.C.", "OTROS", "ACTIVO", "ÑANDÚ ÜBER", 2018, 23),
]
_FLEET_SQL = (
    "INSERT INTO landing.vehicle_fleet_snapshot VALUES (2026, 10, %s, %s, %s, %s, %s, %s, %s, "
    "'mintransporte_runt_parque', %s, %s)"
)
_FLEET_COLUMNS = (
    "publication_year, publication_month, department_name, municipality_name, service_name, "
    "vehicle_status, vehicle_class, registration_year, vehicle_count, source_system, "
    "source_reference, load_id, department_name_norm, municipality_name_norm, vehicle_class_norm"
)
_FX_SQL = "INSERT INTO landing.fx_rate VALUES (%s, 'USD', 'COP', %s, 'superfinanciera_trm', %s, %s)"
_FX_COLUMNS = (
    "rate_date::text, currency_from, currency_to, rate::text, source_system, source_reference, "
    "load_id"
)


@pytest.fixture
def warehouse(pg_settings):
    run_migrate(pg_settings)
    loader = connect(pg_settings, Profile.LOADER, autocommit=True)
    admin = connect(pg_settings, Profile.ADMIN, autocommit=True)
    load_id = loader.execute(_LOAD_RUN_SQL, (HASH, HASH, HASH, str(uuid.uuid4()))).fetchone()[0]
    for day, rate in zip(DAYS, RATES, strict=True):
        loader.execute(_FX_SQL, (day, rate, f"raw/{day}", load_id))
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
    state = {"settings": settings}
    monkeypatch.setattr(tcli, "settings_factory", lambda env: state["settings"])

    def run(command, settings=None, select=None):
        state["settings"] = settings or warehouse[0]
        capfd.readouterr()  # drop output of earlier invocations
        args = ["transform", command, *(["--select", select] if select else [])]
        result = runner.invoke(app, args)
        captured = capfd.readouterr()
        return result.exit_code, result.output + captured.out + captured.err

    run.project = project
    return run


def _mart(settings):
    reader = connect(settings, Profile.READER, autocommit=True)
    try:
        return reader.execute(
            f"SELECT {_FX_COLUMNS} FROM marts.fct_fx_rate_daily ORDER BY 1"
        ).fetchall()
    finally:
        reader.close()


def _landing(admin):
    return admin.execute(f"SELECT {_FX_COLUMNS} FROM landing.fx_rate ORDER BY 1").fetchall()


def test_build_mart_equals_landing_and_is_repeatable(warehouse, transform):
    settings, _, admin = warehouse
    code, output = transform("build")
    assert code == 0, output
    first = _mart(settings)
    assert first == _landing(admin) and len(first) == len(DAYS)  # values, not just counts
    code, output = transform("build")
    assert code == 0, output
    assert _mart(settings) == first


def test_date_gap_fails_and_keeps_previous_mart(warehouse, transform):
    settings, loader, admin = warehouse
    code, output = transform("build")
    assert code == 0, output
    before = _mart(settings)
    load_id = before[0][-1]

    admin.execute("DELETE FROM landing.fx_rate WHERE rate_date = '2026-01-03'")
    code, output = transform("build")
    assert code == 1
    assert "assert_fx_rate_daily_contiguous" in output
    assert "SKIP" in output
    assert _mart(settings) == before  # mart skipped, previous one intact

    loader.execute(_FX_SQL, ("2026-01-03", RATES[2], "raw/2026-01-03", load_id))
    code, output = transform("build")
    assert code == 0, output
    assert _mart(settings) == before


def test_freshness_thresholds(warehouse, fleet, transform):
    # Unselected freshness evaluates every source, so the fleet one needs a load_run too.
    _, _, admin = warehouse
    assert transform("freshness")[0] == 0  # just loaded
    admin.execute("UPDATE ops.load_run SET loaded_at = now() - interval '3 days'")
    code, output = transform("freshness")
    assert code == 0, output  # warn_after (2 days) only warns
    assert "WARN" in output
    admin.execute("UPDATE ops.load_run SET loaded_at = now() - interval '8 days'")
    code, output = transform("freshness")
    assert code == 1, output  # error_after (7 days)
    assert "ERROR STALE" in output


def test_wrong_port_is_transient(warehouse, transform):
    settings = dataclasses.replace(warehouse[0], port=1)
    code, output = transform("build", settings)
    assert code == 3
    assert settings.transformer_password not in output


def test_lock_held_by_another_session_is_transient(warehouse, transform):
    settings = warehouse[0]
    holder = connect(settings, Profile.TRANSFORMER, autocommit=True)
    holder.execute("SELECT pg_advisory_lock(%s)", (rn.TRANSFORM_LOCK_KEY,))
    try:
        code, output = transform("build")
        assert code == 3 and "lock" in output
    finally:
        holder.close()
    assert transform("build")[0] == 0  # released with the session


def test_password_never_reaches_output_or_dbt_files(warehouse, transform):
    secret = warehouse[0].transformer_password
    outputs = [transform("build")[1], transform("freshness")[1]]
    assert all(secret not in text for text in outputs)
    files = [p for p in transform.project.rglob("*") if p.is_file()]
    assert any(p.name == "partial_parse.msgpack" for p in files)
    assert any(p.parent.name == "logs" for p in files)
    leaking = [p for p in files if secret.encode() in p.read_bytes()]
    assert leaking == []


def test_reader_sees_marts_but_not_staging(warehouse, transform):
    settings = warehouse[0]
    assert transform("build")[0] == 0
    reader = connect(settings, Profile.READER, autocommit=True)
    try:
        count = reader.execute("SELECT count(*) FROM marts.fct_fx_rate_daily").fetchone()
        assert count == (len(DAYS),)
        with pytest.raises(pgerr.InsufficientPrivilege):
            reader.execute("SELECT count(*) FROM staging.stg_fx_rate")
    finally:
        reader.close()


# --- vehicle fleet (D100, D101) ---------------------------------------------------------------


@pytest.fixture
def fleet(warehouse):
    """The fx_rate warehouse plus one fleet publication (2026-10) with messy spellings."""
    _, loader, admin = warehouse
    load_id = loader.execute(
        _FLEET_RUN_SQL, (FLEET_HASH, FLEET_HASH, FLEET_HASH, len(FLEET), str(uuid.uuid4()))
    ).fetchone()[0]
    for i, row in enumerate(FLEET):
        loader.execute(_FLEET_SQL, (*row, f"raw/fleet#{i}", load_id))
    return admin, load_id


def _fleet_mart(settings):
    reader = connect(settings, Profile.READER, autocommit=True)
    try:
        return reader.execute(
            f"SELECT {_FLEET_COLUMNS} FROM marts.fct_vehicle_fleet_snapshot "
            "ORDER BY 1, 2, 3, 4, 5, 6, 7, 8"
        ).fetchall()
    finally:
        reader.close()


def test_fleet_build_normalizes_and_keeps_every_original_row(warehouse, fleet, transform):
    settings = warehouse[0]
    code, output = transform("build", select="tag:vehicle_fleet")
    assert code == 0, output
    assert "fct_fx_rate_daily" not in output  # fx_rate was not selected
    rows = _fleet_mart(settings)
    assert len(rows) == len(FLEET)
    assert sum(r[8] for r in rows) == sum(r[-1] for r in FLEET)
    assert {r[2] for r in rows} == {r[0] for r in FLEET}  # originals untouched
    dep, mun, cls = ({r[i] for r in rows} for i in (12, 13, 14))
    assert dep == {"NARINO", "ARCHIPIELAGO DE SAN ANDRES, PROVIDENCIA", "BOGOTA, D.C."}
    assert mun == {"PASTO", "SAN ANDRES", "BOGOTA, D.C."}
    assert cls == {"CAMION", "CAMION PESADO", "MOTOCICLETA", "AUTOMOVIL (4X4)", "NANDU UBER"}
    assert {r[4] for r in rows} == {"PARTICULAR", "PÚBLICO", "OFICIAL", "NO REGISTRA", "OTROS"}
    assert {r[5] for r in rows} == {"ACTIVO", "INCONSISTENTE"}  # nothing filtered
    again = transform("build", select="tag:vehicle_fleet")
    assert again[0] == 0, again[1]
    assert _fleet_mart(settings) == rows


def test_new_service_fails_staging_skips_mart_and_spares_fx_rate(warehouse, fleet, transform):
    settings = warehouse[0]
    admin, _ = fleet
    assert transform("build", select="tag:vehicle_fleet")[0] == 0
    before = _fleet_mart(settings)
    admin.execute(
        "UPDATE landing.vehicle_fleet_snapshot SET service_name = 'ESPECIAL' "
        "WHERE municipality_name = 'SAN ANDRES'"
    )
    code, output = transform("build", select="tag:vehicle_fleet")
    assert code == 1
    assert "accepted_values_landing_vehicle_fleet_snapshot_service_name" in output
    assert "SKIP" in output and "fct_vehicle_fleet_snapshot" in output
    assert _fleet_mart(settings) == before  # previous mart intact
    code, output = transform("build", select="tag:fx_rate")
    assert code == 0, output
    assert "fct_fx_rate_daily" in output and "vehicle_fleet" not in output


# Every case also changes landing data the mart would copy if it were rebuilt, so "mart intact"
# cannot pass by coincidence (an unchanged landing would rebuild an identical mart).
_BUMP_COUNTS = "UPDATE landing.vehicle_fleet_snapshot SET vehicle_count = vehicle_count + 1"
_OLDER_LOAD_RUN = (
    "UPDATE landing.vehicle_fleet_snapshot SET load_id = ("
    "SELECT min(load_id) FROM ops.load_run WHERE dataset = 'fx_rate') "
    "WHERE municipality_name = 'SAN ANDRES'"
)
_NEWER_LOAD_RUN = (
    "INSERT INTO ops.load_run (dataset, source_system, input_fingerprint, transform_name, "
    "rules_version, manifest_key, manifest_sha256, csv_key, csv_sha256, csv_size_bytes, "
    "row_count, coverage_from, coverage_to, last_input_batch_id, last_input_extraction_date, "
    "last_input_finished_at, normalized_manifest, loader_version) VALUES "
    "('vehicle_fleet_snapshot', 'mintransporte_runt_parque', repeat('c', 64), 't', '1', 'k', "
    "repeat('c', 64), 'c', repeat('c', 64), 1, 7, '2026-10-01', '2026-10-01', "
    "'00000000-0000-0000-0000-000000000000', '2026-10-01', now(), '{}'::jsonb, '0.1')"
)


@pytest.mark.parametrize(
    "statements",
    [
        (
            "UPDATE ops.load_run SET row_count = row_count + 1 "
            "WHERE dataset = 'vehicle_fleet_snapshot'",
            _BUMP_COUNTS,
        ),
        # a row left behind by an older load: min(load_id) differs from the latest load_run
        (_OLDER_LOAD_RUN,),
        # a newer load_run than the rows' load_id: max(load_id) differs
        (_NEWER_LOAD_RUN, _BUMP_COUNTS),
    ],
    ids=["row_count", "min_load_id", "newer_load_run"],
)
def test_fleet_rows_must_match_their_latest_load_run(warehouse, fleet, transform, statements):
    """assert_vehicle_fleet_rows_match_load_run fails the build and, through the depends_on hint
    of the mart (two-parent test, D87 pattern), leaves the previous mart intact (SKIP)."""
    settings = warehouse[0]
    admin, _ = fleet
    assert transform("build", select="tag:vehicle_fleet")[0] == 0
    before = _fleet_mart(settings)
    for statement in statements:
        admin.execute(statement)
    code, output = transform("build", select="tag:vehicle_fleet")
    assert code == 1
    assert "assert_vehicle_fleet_rows_match_load_run" in output
    assert re.search(r"SKIP.*fct_vehicle_fleet_snapshot", output)
    assert _fleet_mart(settings) == before


@pytest.mark.parametrize(
    ("statement", "failing_test"),
    [
        (
            "UPDATE landing.vehicle_fleet_snapshot SET department_name = 'NARIÑO @' "
            "WHERE municipality_name = 'SAN ANDRES'",
            "assert_vehicle_fleet_norm_charset",
        ),
        (
            "UPDATE landing.vehicle_fleet_snapshot SET vehicle_status = 'ELIMINADO' "
            "WHERE municipality_name = 'SAN ANDRES'",
            "accepted_values_landing_vehicle_fleet_snapshot_vehicle_status",
        ),
    ],
)
def test_fleet_singular_and_status_tests_block_the_mart(
    warehouse, fleet, transform, statement, failing_test
):
    settings = warehouse[0]
    admin, _ = fleet
    assert transform("build", select="tag:vehicle_fleet")[0] == 0
    before = _fleet_mart(settings)
    admin.execute(statement)
    code, output = transform("build", select="tag:vehicle_fleet")
    assert code == 1
    assert failing_test in output and "SKIP" in output
    assert _fleet_mart(settings) == before


def test_freshness_select_evaluates_only_its_own_source(fleet, transform):
    admin, _ = fleet
    only_fleet = r"ops\.load_run_fleet"
    only_fx = r"ops\.load_run(?!_fleet)"
    code, output = transform("freshness", select="tag:vehicle_fleet")
    assert code == 0, output
    assert re.search(only_fleet, output) and re.search(only_fx, output) is None
    code, output = transform("freshness", select="tag:fx_rate")
    assert code == 0, output
    assert re.search(only_fx, output) and re.search(only_fleet, output) is None

    admin.execute(
        "UPDATE ops.load_run SET loaded_at = now() - interval '40 days' "
        "WHERE dataset = 'vehicle_fleet_snapshot'"
    )
    code, output = transform("freshness", select="tag:vehicle_fleet")
    assert code == 0 and "WARN" in output  # warn_after 35 days
    assert transform("freshness", select="tag:fx_rate")[0] == 0  # unaffected
    admin.execute(
        "UPDATE ops.load_run SET loaded_at = now() - interval '70 days' "
        "WHERE dataset = 'vehicle_fleet_snapshot'"
    )
    code, output = transform("freshness", select="tag:vehicle_fleet")
    assert code == 1 and "ERROR STALE" in output  # error_after 65 days
    assert transform("freshness", select="tag:fx_rate")[0] == 0


@pytest.mark.parametrize("command", ["build", "freshness"])
@pytest.mark.parametrize("selector", ["fct_fx_rate_daily", "tag:fx_rate+", "path:models"])
def test_selector_outside_allow_list_is_exit_2_and_runs_nothing(
    warehouse, transform, command, selector
):
    code, _ = transform(command, select=selector)
    assert code == 2
    reader = connect(warehouse[0], Profile.READER, autocommit=True)
    try:
        with pytest.raises(pgerr.UndefinedTable):
            reader.execute("SELECT 1 FROM marts.fct_fx_rate_daily")
    finally:
        reader.close()

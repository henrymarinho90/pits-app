"""`pits transform` end to end against a per-test database (D85-D88, D87 tests of the project).

The real CLI and the real dbt subprocess run; only the settings (test database, suffixed
transformer role, in-memory password) and the project directory are injected. The dbt project
is COPIED to tmp_path per test, so target/ and logs/ never touch the repository checkout.
"""

from __future__ import annotations

import dataclasses
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

    def run(command, settings=None):
        state["settings"] = settings or warehouse[0]
        capfd.readouterr()  # drop output of earlier invocations
        result = runner.invoke(app, ["transform", command])
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


def test_freshness_thresholds(warehouse, transform):
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

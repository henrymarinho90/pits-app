"""Shared fixtures for the `pits load vehicle-fleet` tests against a real Postgres 17 (D99).

Imported by test_vehicle_fleet_load_pg.py (`tests/pg` is on pythonpath). `warehouse` migrates a
per-test database, points the load CLI at it with an in-memory normalized store holding two real
publications (2026-09 with two parts, 2026-10 with accents/quotes/commas) written by the real
normalizer, and yields an admin connection (autocommit).
"""

from __future__ import annotations

import pytest
from fleet_artifact_support import RAW_BUCKET, build_raw_and_normalized
from typer.testing import CliRunner

from pits.cli import app
from pits.ingestion.raw_store import MemoryRawStore
from pits.warehouse import load_cli
from pits.warehouse.connection import connect
from pits.warehouse.migrate import run_migrate
from pits.warehouse.settings import Profile

runner = CliRunner()
BIG_ROWS = 25_000  # above MAX_PART_ROWS (20_000): the 2026-09 artifact has two parts


@pytest.fixture(scope="module")
def fleet_artifacts():
    """(raw objects, normalized objects, {publication: FleetResult}); copied per test."""
    raw, norm, results = build_raw_and_normalized(big=BIG_ROWS)
    return dict(raw.objects), dict(norm.objects), results


@pytest.fixture
def raw_store(fleet_artifacts):
    memory = MemoryRawStore()
    memory.objects = dict(fleet_artifacts[0])
    return memory


@pytest.fixture
def store(fleet_artifacts):
    memory = MemoryRawStore()
    memory.objects = dict(fleet_artifacts[1])
    return memory


@pytest.fixture
def results(fleet_artifacts):
    return fleet_artifacts[2]


@pytest.fixture
def warehouse(pg_settings, monkeypatch, store):
    run_migrate(pg_settings)  # real packaged migrations
    for key, value in {
        "S3_ENDPOINT_URL": "http://127.0.0.1:1",
        "PITS_S3_READER_ACCESS_KEY_ID": "READERKEYEXAMPLE0001",
        "PITS_S3_READER_SECRET_ACCESS_KEY": "s3-secret-0123456789-abcdefghijklmnop",
        "S3_RAW_BUCKET": RAW_BUCKET,
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(load_cli, "client_factory", lambda s: object())
    monkeypatch.setattr(load_cli, "store_factory", lambda c, b: store)
    monkeypatch.setattr(load_cli, "settings_factory", lambda env: pg_settings)
    admin = connect(pg_settings, Profile.ADMIN, autocommit=True)
    yield admin
    admin.close()


def load(*args):
    return runner.invoke(app, ["load", "vehicle-fleet", *args])


def fields(output: str) -> list[dict[str, str]]:
    """One dict per `outcome=...` line, in output order."""
    return [
        dict(part.split("=", 1) for part in line.split())
        for line in output.splitlines()
        if line.startswith("outcome=")
    ]

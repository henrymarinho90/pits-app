"""Shared fixtures for the `pits load fx-rate` tests against a real Postgres 17.

Imported by test_fx_rate_load_pg.py and test_warehouse_lock_pg.py (`tests/pg` is on pythonpath).
`warehouse` migrates a per-test database, points the load CLI at it with an in-memory
raw store, and yields an admin connection (autocommit).
"""

from __future__ import annotations

from datetime import date

import pytest
from trm_helpers import B1, put_raw_batch, raw_row
from typer.testing import CliRunner

from pits.cli import app
from pits.ingestion.raw_store import MemoryRawStore
from pits.sources.trm.contract import BACKFILL_FROM
from pits.sources.trm.normalize import normalize_trm
from pits.warehouse import load_cli
from pits.warehouse.connection import connect
from pits.warehouse.migrate import run_migrate
from pits.warehouse.settings import Profile

runner = CliRunner()
RAW_BUCKET = "pits-raw"
LAST_DAY = date(2026, 10, 13)


@pytest.fixture(scope="module")
def base_artifact():
    """(objects, NormalizeResult) written by the real normalizer; copied per test."""
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_raw_batch(
        raw,
        B1,
        date(2026, 10, 9),
        "full",
        [
            raw_row(BACKFILL_FROM, date(2026, 10, 9), "3000.5"),
            raw_row(date(2026, 10, 10), LAST_DAY, "3194.44"),
        ],
    )
    result = normalize_trm(raw, norm, raw_bucket=RAW_BUCKET)
    return dict(norm.objects), result


@pytest.fixture
def store(base_artifact):
    memory = MemoryRawStore()
    memory.objects = dict(base_artifact[0])
    return memory


@pytest.fixture
def base(base_artifact):
    return base_artifact[1]


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
    return runner.invoke(app, ["load", "fx-rate", *args])

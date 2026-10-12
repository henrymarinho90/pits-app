"""Fixtures for tests against a local Postgres 17 (`-m pg`, D84).

Imported by tests/pg/conftest.py and by tests/contract/test_fx_rate_load_e2e.py
(`tests/pg` is on pythonpath).

Isolation: roles are cluster-global, so every test gets its OWN database
`pits_test_<uuid8>` and its OWN suffixed roles (`pits_owner_t<uuid8>`, ...). The real
`pits_warehouse` database and the real `pits_owner/pits_loader/pits_reader` roles are never
touched. Loader/reader/transformer passwords are random per test and only live in memory.
Teardown drops the database and the roles. Only loopback (never the compose host `postgres`, D91)
and a port != 5432 are accepted: the guards live in `_admin_base` and run before any
connection (orphan sweep included).
Run: `uv run --env-file ../pits-app/.env pytest -m pg -q` (admin = POSTGRES_USER/PASSWORD).
"""

from __future__ import annotations

import dataclasses
import os
import re
import secrets
import uuid

import pytest
from psycopg import sql

from pits.warehouse.connection import connect
from pits.warehouse.errors import WarehouseConfigError
from pits.warehouse.settings import Profile, RoleNames, WarehouseSettings, load_warehouse_settings

REAL_DB = "pits_warehouse"
_PG_TEST_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
# Only names that match these EXACTLY (uuid8 suffix) may ever be swept; real names never match.
_ORPHAN_DB_RE = re.compile(r"pits_test_[0-9a-f]{8}")
_ORPHAN_ROLE_RE = re.compile(r"pits_(?:owner|loader|reader|transformer)_t[0-9a-f]{8}")


def _admin_base() -> WarehouseSettings:
    """Admin settings for pg tests; shared by the orphan sweep and `pg_settings`.

    Guards run BEFORE any connection: D84/D91 pg tests only talk to a loopback Postgres on a
    port != 5432, never to the compose-internal host. Messages never include values.
    """
    try:
        base = load_warehouse_settings(os.environ, [Profile.ADMIN])
    except WarehouseConfigError as exc:
        pytest.fail(f"pg tests need POSTGRES_USER/POSTGRES_PASSWORD (use --env-file): {exc}")
    if base.host not in _PG_TEST_HOSTS:
        pytest.fail("pg tests accept loopback hosts only (D84/D91)")
    if base.port == 5432:
        pytest.fail("pg tests must not use port 5432 (D84)")
    return base


@pytest.fixture(scope="session", autouse=True)
def _sweep_orphans():
    """Drop databases/roles left by a crashed earlier session (never the real ones)."""
    admin = connect(_admin_base(), Profile.ADMIN, dbname="postgres", autocommit=True)
    try:
        dbs = [r[0] for r in admin.execute("SELECT datname FROM pg_database")]
        roles = [r[0] for r in admin.execute("SELECT rolname FROM pg_roles")]
        for db in dbs:
            if _ORPHAN_DB_RE.fullmatch(db) and db != REAL_DB:
                admin.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(db))
                )
        for role in roles:
            if _ORPHAN_ROLE_RE.fullmatch(role):
                admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
    finally:
        admin.close()


@pytest.fixture
def pg_settings():
    base = _admin_base()
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
    assert settings.dbname != REAL_DB
    yield settings
    _cleanup(settings)


def _cleanup(settings: WarehouseSettings) -> None:
    admin = connect(settings, Profile.ADMIN, dbname="postgres", autocommit=True)
    try:
        db = sql.Identifier(settings.dbname)
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(db))
        for role in (
            settings.roles.transformer,
            settings.roles.loader,
            settings.roles.reader,
            settings.roles.owner,
        ):
            admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
    finally:
        admin.close()

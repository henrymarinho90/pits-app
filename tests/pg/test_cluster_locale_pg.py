"""D112: the pg cluster (local or CI) must have the same locale as production compose.

template1 is what CREATE DATABASE clones, so it must also be builtin C.UTF-8 / UTF8.
"""

from __future__ import annotations

import pytest

from pits.warehouse.bootstrap import bootstrap
from pits.warehouse.connection import connect
from pits.warehouse.settings import Profile

QUERY = (
    "SELECT datlocprovider, datlocale, pg_encoding_to_char(encoding) "
    "FROM pg_database WHERE datname = %s"
)


@pytest.mark.parametrize("via_bootstrap", [False, True], ids=["template1", "test_db"])
def test_database_uses_builtin_c_utf8(pg_settings, via_bootstrap):
    if via_bootstrap:
        bootstrap(pg_settings)
    name = pg_settings.dbname if via_bootstrap else "template1"
    with connect(pg_settings, Profile.ADMIN, dbname="postgres", autocommit=True) as conn:
        row = conn.execute(QUERY, (name,)).fetchone()
    assert row == ("b", "C.UTF-8", "UTF8")

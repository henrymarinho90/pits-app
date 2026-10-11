"""Fixtures for `-m pg` tests; the implementation lives in pg_support.py (see its docstring)."""

import pytest
from pg_support import _sweep_orphans, pg_settings  # noqa: F401  (fixtures)


def pytest_collection_modifyitems(items):
    for item in items:
        if "tests/pg/" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.pg)

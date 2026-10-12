"""Offline tests for the warehouse write lock of bootstrap/migrate (D90), with fake connections."""

from __future__ import annotations

from contextlib import contextmanager

import psycopg
import pytest

from pits.warehouse import bootstrap as bs
from pits.warehouse import migrate as mg
from pits.warehouse.errors import WarehouseTransientError
from pits.warehouse.locks import WAREHOUSE_LOCK_KEY


class _Cursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _LockConn:
    """Admin connection to the warehouse database; records the lock calls in `events`."""

    def __init__(self, events, *, lock_free=True):
        self._events = events
        self._lock_free = lock_free
        self.closed = False

    def execute(self, query, params=None):
        if "pg_try_advisory_lock" in query:
            assert params == (WAREHOUSE_LOCK_KEY,)
            self._events.append("lock")
            return _Cursor((self._lock_free,))
        if "pg_advisory_unlock" in query:
            assert params == (WAREHOUSE_LOCK_KEY,)
            self._events.append("unlock")
            return _Cursor((True,))
        raise AssertionError(f"unexpected query: {query}")

    def close(self):
        self.closed = True
        self._events.append("close_lock_conn")


class _TargetConn:
    def __init__(self, events):
        self._events = events

    def commit(self):
        self._events.append("commit_objects")

    def close(self):
        pass


class _Events(list):
    def __init__(self):
        super().__init__()
        self.state = {"lock_free": True, "lock_conn": None}


@pytest.fixture
def events(monkeypatch):
    log = _Events()
    state = log.state

    def fake_connect(settings, profile, **kwargs):
        if kwargs.get("application_name") == "pits-migrate-lock":
            state["lock_conn"] = _LockConn(log, lock_free=state["lock_free"])
            return state["lock_conn"]
        return _TargetConn(log)

    monkeypatch.setattr(bs, "connect", fake_connect)
    monkeypatch.setattr(bs, "_bootstrap_roles", lambda c, s: log.append("roles"))
    monkeypatch.setattr(bs, "_bootstrap_database", lambda c, s: log.append("create_database"))
    monkeypatch.setattr(bs, "_bootstrap_objects", lambda c, s: log.append("objects"))
    monkeypatch.setattr(bs, "_set_timeouts", lambda c: None)
    return log


def test_lock_is_taken_after_creating_the_database_and_before_the_objects(events):
    with bs.bootstrap_locked(object(), object()):
        events.append("body")
    assert events == [
        "roles",
        "create_database",
        "lock",
        "objects",
        "commit_objects",
        "body",
        "unlock",
        "close_lock_conn",
    ]


def test_lock_is_released_when_the_body_fails(events):
    with pytest.raises(RuntimeError, match="boom"), bs.bootstrap_locked(object(), object()):
        raise RuntimeError("boom")
    assert events[-2:] == ["unlock", "close_lock_conn"]
    assert events.state["lock_conn"].closed


def test_lock_is_released_when_the_objects_fail(events, monkeypatch):
    def fail(conn, settings):
        raise RuntimeError("objects failed")

    monkeypatch.setattr(bs, "_bootstrap_objects", fail)
    with (
        pytest.raises(RuntimeError, match="objects failed"),
        bs.bootstrap_locked(object(), object()),
    ):
        pytest.fail("body must not run")
    assert events[-2:] == ["unlock", "close_lock_conn"]


def test_busy_lock_is_transient_and_writes_no_objects(events):
    events.state["lock_free"] = False
    with (
        pytest.raises(WarehouseTransientError, match="holds the lock"),
        bs.bootstrap_locked(object(), object()),
    ):
        pytest.fail("body must not run")
    assert "objects" not in events and "commit_objects" not in events
    assert "unlock" not in events  # never held, so never released
    assert events[-1] == "close_lock_conn"


def test_run_migrate_busy_lock_applies_nothing(events, monkeypatch):
    @contextmanager
    def fake_run_lock(settings):
        yield object()

    applied: list[str] = []
    monkeypatch.setattr(mg, "run_lock", fake_run_lock)
    monkeypatch.setattr(mg, "discover_migrations", lambda source=None: [])
    monkeypatch.setattr(mg, "connect", lambda *a, **k: applied.append("admin_conn"))
    monkeypatch.setattr(mg, "apply_migrations", lambda *a: applied.append("apply"))
    events.state["lock_free"] = False
    with pytest.raises(WarehouseTransientError):
        mg.run_migrate(object())
    assert applied == []
    assert "objects" not in events


def test_run_migrate_holds_the_lock_until_the_last_migration(events, monkeypatch):
    class _Admin:
        def close(self):
            events.append("close_admin")

    @contextmanager
    def fake_run_lock(settings):
        yield object()

    monkeypatch.setattr(mg, "run_lock", fake_run_lock)
    monkeypatch.setattr(mg, "discover_migrations", lambda source=None: [])
    monkeypatch.setattr(mg, "connect", lambda *a, **k: _Admin())
    monkeypatch.setattr(
        mg, "apply_migrations", lambda conn, migrations, roles: events.append("migrations")
    )
    settings = type("S", (), {"roles": None})()
    mg.run_migrate(settings)
    assert events.index("lock") < events.index("objects") < events.index("migrations")
    assert events.index("migrations") < events.index("unlock")
    assert events[-1] == "close_lock_conn"


def test_psycopg_error_taking_the_lock_is_mapped_to_a_warehouse_error(events, monkeypatch):
    class _Failing(_LockConn):
        def execute(self, query, params=None):
            raise psycopg.OperationalError("server closed the connection")

    mapped = WarehouseTransientError("mapped")
    seen = []

    def fake_map(exc, context):
        seen.append((type(exc), context))
        return mapped

    monkeypatch.setattr(bs, "connect", lambda *a, **k: _Failing(events))
    monkeypatch.setattr(bs, "to_warehouse_error", fake_map)
    with pytest.raises(WarehouseTransientError) as info, bs.warehouse_lock(object()):
        pytest.fail("body must not run")
    assert info.value is mapped
    assert seen == [(psycopg.OperationalError, "warehouse lock")]
    assert events[-1] == "close_lock_conn"

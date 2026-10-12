"""Offline guards of the pg test support (D84/D91): they must fail BEFORE connecting."""

import pg_support
import pytest

PW = "sentinel-admin-pw-0123456789"


@pytest.fixture
def no_connect(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("must not connect")

    monkeypatch.setattr(pg_support, "connect", boom)


def _env(monkeypatch, **extra):
    for name in ("PITS_PG_HOST", "POSTGRES_HOST_PORT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("POSTGRES_USER", "pits")
    monkeypatch.setenv("POSTGRES_PASSWORD", PW)
    for name, value in extra.items():
        monkeypatch.setenv(name, value)


@pytest.mark.parametrize("port", ["5432", "5433"])
def test_admin_base_rejects_compose_host(monkeypatch, no_connect, port):
    _env(monkeypatch, PITS_PG_HOST="postgres", POSTGRES_HOST_PORT=port)
    with pytest.raises(pytest.fail.Exception, match="loopback hosts only") as info:
        pg_support._admin_base()
    assert PW not in str(info.value)


def test_admin_base_accepts_loopback_default(monkeypatch):
    _env(monkeypatch)
    base = pg_support._admin_base()
    assert (base.host, base.port) == ("127.0.0.1", 5433)

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from pits.warehouse.connection import (
    _FORBIDDEN_ENV,
    build_conninfo,
    check_environment,
    classify_connect_error,
    verify_server,
)
from pits.warehouse.errors import (
    WarehouseConfigError,
    WarehousePermanentError,
    WarehouseTransientError,
)
from pits.warehouse.settings import Profile, load_warehouse_settings

PASSWORD = "sentinel-loader-pw-0123456789"


class _Cursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Conn:
    def __init__(self, row):
        self._row = row

    def execute(self, _query):
        return _Cursor(self._row)


def _settings():
    return load_warehouse_settings({"PITS_PG_LOADER_PASSWORD": PASSWORD})


def test_conninfo_is_fully_explicit():
    info = conninfo_to_dict(
        build_conninfo(_settings(), Profile.LOADER, application_name="pits-load")
    )
    assert info["host"] == "127.0.0.1"
    assert info["port"] == "5433"
    assert info["dbname"] == "pits_warehouse"
    assert info["user"] == "pits_loader"
    assert info["password"] == PASSWORD
    assert info["application_name"] == "pits-load"
    assert info["sslmode"] == "disable"
    assert int(info["connect_timeout"]) > 0
    assert info["client_encoding"] == "UTF8"
    assert info["options"] == "-c TimeZone=UTC -c DateStyle=ISO"


def test_conninfo_dbname_override():
    info = conninfo_to_dict(build_conninfo(_settings(), Profile.LOADER, dbname="postgres"))
    assert info["dbname"] == "postgres"


@pytest.mark.parametrize("name", _FORBIDDEN_ENV)
def test_rejects_dangerous_libpq_env(name):
    with pytest.raises(WarehouseConfigError, match=name):
        check_environment({name: "x"})


def test_accepts_clean_env_and_overridable_vars():
    check_environment({"PGHOST": "evil", "PGPASSWORD": "x", "PGUSER": "y"})


def test_verify_server_ok():
    verify_server(_Conn((170004, "pits_warehouse")), "pits_warehouse")


def test_verify_server_wrong_major():
    with pytest.raises(WarehousePermanentError, match="major version 16"):
        verify_server(_Conn((160009, "pits_warehouse")), "pits_warehouse")


def test_verify_server_wrong_database():
    with pytest.raises(WarehousePermanentError, match="unexpected database"):
        verify_server(_Conn((170004, "postgres")), "pits_warehouse")


class _PgConn:
    def __init__(self, **attrs):
        self.used_password = False
        self.needs_password = False
        self.__dict__.update(attrs)


def _op_error(pgconn):
    return psycopg.OperationalError("connection failed", pgconn=pgconn)


def test_connect_error_without_pgconn_is_transient():
    err = classify_connect_error(_op_error(None), "connect as loader")
    assert isinstance(err, WarehouseTransientError)


def test_connect_error_before_authentication_is_transient():
    err = classify_connect_error(_op_error(_PgConn()), "connect as loader")
    assert isinstance(err, WarehouseTransientError)


@pytest.mark.parametrize("attr", ["used_password", "needs_password"])
def test_connect_error_after_password_exchange_is_permanent(attr):
    err = classify_connect_error(_op_error(_PgConn(**{attr: True})), "connect as loader")
    assert isinstance(err, WarehousePermanentError)
    assert "OperationalError" in str(err)


def test_connect_error_with_sqlstate_uses_sqlstate_rules():
    from psycopg import errors as pgerr

    err = classify_connect_error(pgerr.CannotConnectNow("x"), "connect as loader")
    assert isinstance(err, WarehouseTransientError)
    err = classify_connect_error(pgerr.InvalidPassword("x"), "connect as loader")
    assert isinstance(err, WarehousePermanentError)


# TODO(S5): tests/pg must cover "wrong password -> exit 1" against a real server.

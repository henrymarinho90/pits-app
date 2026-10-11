import psycopg
import pytest
from psycopg import errors as pgerr

from pits.warehouse.errors import (
    ErrorKind,
    WarehousePermanentError,
    WarehouseTransientError,
    classify_error,
    describe_error,
    to_warehouse_error,
)

SENTINEL = "sentinel-secret-0123456789"

TRANSIENT = [
    pgerr.LockNotAvailable,  # 55P03
    pgerr.SerializationFailure,  # 40001
    pgerr.DeadlockDetected,  # 40P01
    pgerr.AdminShutdown,  # 57P01
    pgerr.CannotConnectNow,  # 57P03
    pgerr.CrashShutdown,  # 57P02
    pgerr.TooManyConnections,  # 53300
    pgerr.ConnectionFailure,  # 08006
    pgerr.ConnectionException,  # 08000
]
PERMANENT = [
    pgerr.InvalidPassword,  # 28P01
    pgerr.InvalidAuthorizationSpecification,  # 28000
    pgerr.InsufficientPrivilege,  # 42501
    pgerr.UniqueViolation,  # 23505
    pgerr.CheckViolation,  # 23514
    pgerr.ForeignKeyViolation,  # 23503
    pgerr.NotNullViolation,  # 23502
    pgerr.UndefinedTable,  # 42P01
    pgerr.SyntaxError,  # 42601
    pgerr.QueryCanceled,  # 57014 (statement_timeout)
    pgerr.DataError,
]


@pytest.mark.parametrize("cls", TRANSIENT, ids=lambda c: c.__name__)
def test_transient(cls):
    assert classify_error(cls("x")) is ErrorKind.TRANSIENT


@pytest.mark.parametrize("cls", PERMANENT, ids=lambda c: c.__name__)
def test_permanent(cls):
    assert classify_error(cls("x")) is ErrorKind.PERMANENT


def test_sqlstates_are_the_expected_ones():
    assert pgerr.LockNotAvailable.sqlstate == "55P03"
    assert pgerr.SerializationFailure.sqlstate == "40001"
    assert pgerr.DeadlockDetected.sqlstate == "40P01"
    assert pgerr.AdminShutdown.sqlstate == "57P01"
    assert pgerr.CannotConnectNow.sqlstate == "57P03"
    assert pgerr.InvalidPassword.sqlstate == "28P01"
    assert pgerr.InsufficientPrivilege.sqlstate == "42501"


def test_connection_refused_without_sqlstate_is_transient():
    exc = psycopg.OperationalError("connection refused")
    assert exc.sqlstate is None
    assert classify_error(exc) is ErrorKind.TRANSIENT


def test_interface_error_is_transient():
    assert classify_error(psycopg.InterfaceError("connection already closed")) is (
        ErrorKind.TRANSIENT
    )


def test_unknown_errors_are_permanent():
    assert classify_error(ValueError("x")) is ErrorKind.PERMANENT
    assert classify_error(psycopg.ProgrammingError("x")) is ErrorKind.PERMANENT


def test_warehouse_transient_error_is_transient():
    assert classify_error(WarehouseTransientError("x")) is ErrorKind.TRANSIENT
    assert classify_error(WarehousePermanentError("x")) is ErrorKind.PERMANENT


def test_to_warehouse_error_types():
    assert isinstance(
        to_warehouse_error(pgerr.DeadlockDetected("x"), "ctx"), WarehouseTransientError
    )
    assert isinstance(
        to_warehouse_error(pgerr.InvalidPassword("x"), "ctx"), WarehousePermanentError
    )


@pytest.mark.parametrize("cls", [pgerr.InvalidPassword, pgerr.LockNotAvailable])
def test_messages_never_include_driver_text(cls):
    exc = cls(f"password authentication failed host=127.0.0.1 password={SENTINEL}")
    wrapped = to_warehouse_error(exc, "connect as loader")
    assert SENTINEL not in str(wrapped)
    assert SENTINEL not in describe_error(exc)
    assert cls.sqlstate in str(wrapped)

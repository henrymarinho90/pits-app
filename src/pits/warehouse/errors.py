"""Typed warehouse errors and SQLSTATE classification (transient vs permanent).

Messages carry only the error class and SQLSTATE, never driver text, so they cannot
leak connection parameters or secrets.
"""

from __future__ import annotations

from enum import StrEnum

import psycopg


class ErrorKind(StrEnum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"


class WarehouseError(Exception):
    """Base class for warehouse errors."""


class WarehouseConfigError(WarehouseError, ValueError):
    """Invalid or missing warehouse configuration (permanent)."""


class WarehouseTransientError(WarehouseError):
    """Retry may succeed (exit code 3)."""


class WarehousePermanentError(WarehouseError):
    """Retrying will not help (exit code 1)."""


# Exact SQLSTATEs that are transient; class 08 (connection exceptions) handled by prefix.
_TRANSIENT_SQLSTATES = frozenset(
    {
        "55P03",  # lock_not_available
        "40001",  # serialization_failure
        "40P01",  # deadlock_detected
        "57P01",  # admin_shutdown
        "57P02",  # crash_shutdown
        "57P03",  # cannot_connect_now
        "53300",  # too_many_connections
    }
)


def classify_sqlstate(sqlstate: str | None) -> ErrorKind | None:
    """Return the kind for a known SQLSTATE, or None when it says nothing."""
    if not sqlstate:
        return None
    if sqlstate in _TRANSIENT_SQLSTATES or sqlstate.startswith("08"):
        return ErrorKind.TRANSIENT
    # 28P01/28000 (auth), 42501 (privileges), 23xxx (constraints), 42xxx, etc.
    return ErrorKind.PERMANENT


def classify_error(exc: BaseException) -> ErrorKind:
    """Classify an exception; anything unknown is permanent."""
    if isinstance(exc, WarehouseTransientError):
        return ErrorKind.TRANSIENT
    if isinstance(exc, psycopg.Error):
        by_state = classify_sqlstate(exc.sqlstate)
        if by_state is not None:
            return by_state
        # No SQLSTATE: connection refused / dropped (client-side failures).
        if isinstance(exc, psycopg.OperationalError | psycopg.InterfaceError):
            return ErrorKind.TRANSIENT
    return ErrorKind.PERMANENT


def describe_error(exc: BaseException) -> str:
    """Safe one-line description: class name and SQLSTATE only."""
    sqlstate = getattr(exc, "sqlstate", None)
    suffix = f" sqlstate={sqlstate}" if sqlstate else ""
    return f"{type(exc).__name__}{suffix}"


def to_warehouse_error(exc: psycopg.Error, context: str) -> WarehouseError:
    """Wrap a psycopg error in a typed, secret-free warehouse error."""
    message = f"{context}: {describe_error(exc)}"
    if classify_error(exc) is ErrorKind.TRANSIENT:
        return WarehouseTransientError(message)
    return WarehousePermanentError(message)

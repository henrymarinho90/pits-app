"""Strict JSON field readers shared by the raw and normalized manifests.

Exact types (no bool-as-int, no lenient dates) and one error type, StrictJsonError, which
each manifest module wraps into its own permanent error.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class StrictJsonError(ValueError):
    """A JSON value has the wrong shape, type or format."""


def format_datetime(value: datetime) -> str:
    """UTC timestamp with microseconds and a trailing 'Z'."""
    return value.astimezone(UTC).strftime(DATETIME_FORMAT)


def format_date(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def obj(value: Any, keys: set[str], where: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise StrictJsonError(f"{where} must be an object")
    if set(value) != keys:
        missing = sorted(keys - set(value))
        extra = sorted(set(value) - keys)
        raise StrictJsonError(f"{where} has wrong keys (missing={missing}, unexpected={extra})")
    return value


def string(value: Any, where: str) -> str:
    if not isinstance(value, str):
        raise StrictJsonError(f"{where} must be a string")
    return value


def integer(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StrictJsonError(f"{where} must be an integer")
    return value


def boolean(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise StrictJsonError(f"{where} must be a boolean")
    return value


def iso_date(value: Any, where: str) -> date:
    text = string(value, where)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise StrictJsonError(f"{where} must be an ISO date") from exc
    if parsed.isoformat() != text:
        raise StrictJsonError(f"{where} must be an ISO date (YYYY-MM-DD)")
    return parsed


def optional_iso_date(value: Any, where: str) -> date | None:
    return None if value is None else iso_date(value, where)


def utc_datetime(value: Any, where: str) -> datetime:
    text = string(value, where)
    try:
        return datetime.strptime(text, DATETIME_FORMAT).replace(tzinfo=UTC)
    except ValueError as exc:
        raise StrictJsonError(f"{where} must be a UTC timestamp ending in 'Z'") from exc


def array(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise StrictJsonError(f"{where} must be an array")
    return value

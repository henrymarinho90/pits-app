"""Pieces shared by the SODA extractors (TRM, RUNT): error types and metadata checks."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pits.ingestion.manifest import SchemaColumn
from pits.sources.soda.client import SodaClient


class ExtractError(RuntimeError):
    """Base class for extractor failures; messages never contain secrets."""


class ExtractPermanentError(ExtractError):
    """Retrying will not help (schema drift, invalid rows, write conflict, bad manifest)."""


class ExtractTransientError(ExtractError):
    """Retrying later may succeed (network, 5xx, dataset replaced mid-run, empty dataset)."""


def parse_rows_updated_at(meta: dict[str, Any]) -> int:
    value = meta.get("rowsUpdatedAt")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExtractPermanentError("Metadata rowsUpdatedAt is missing or not an integer")
    return value


def check_metadata(soda: SodaClient, dataset_id: str, schema: Sequence[SchemaColumn]) -> int:
    """Validate the non-system column schema exactly; return rowsUpdatedAt."""
    meta = soda.get_metadata(dataset_id)
    columns = meta.get("columns")
    if not isinstance(columns, list) or not all(isinstance(c, dict) for c in columns):
        raise ExtractPermanentError("Metadata has no valid 'columns' list")
    actual = {
        c.get("fieldName"): c.get("dataTypeName")
        for c in columns
        if not str(c.get("fieldName", "")).startswith(":")
    }
    expected = {c.name: c.data_type for c in schema}
    if actual != expected:
        raise ExtractPermanentError(f"Schema drift in metadata: expected {expected}, got {actual}")
    return parse_rows_updated_at(meta)

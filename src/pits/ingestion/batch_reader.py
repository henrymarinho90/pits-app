"""Verified, lazy reading of the payload pages of a committed raw batch (D65, D76).

Each page is checked against its manifest FileEntry (size, sha256, JSON array of objects,
row_count) before it is yielded, so downstream code never sees unverified raw bytes.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from pits.ingestion.manifest import FileEntry, Manifest, ManifestError, sha256_hex
from pits.ingestion.raw_store import RawObjectNotFoundError, RawStore


class PayloadIntegrityError(ManifestError):
    """A payload object does not match its manifest entry (permanent). Never includes row data."""


@dataclass(frozen=True)
class VerifiedPage:
    entry: FileEntry
    body: bytes
    rows: list[dict[str, Any]]


def _verify(entry: FileEntry, body: bytes) -> list[dict[str, Any]]:
    key = entry.key
    if len(body) != entry.size_bytes:
        raise PayloadIntegrityError(
            f"{key}: size mismatch (expected {entry.size_bytes}, got {len(body)})"
        )
    if sha256_hex(body) != entry.sha256:
        raise PayloadIntegrityError(f"{key}: sha256 mismatch")
    try:
        rows = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise PayloadIntegrityError(f"{key}: payload is not valid UTF-8 JSON") from exc
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise PayloadIntegrityError(f"{key}: payload must be a JSON array of objects")
    if len(rows) != entry.row_count:
        raise PayloadIntegrityError(
            f"{key}: row_count mismatch (expected {entry.row_count}, got {len(rows)})"
        )
    return rows


def iter_verified_pages(store: RawStore, manifest: Manifest) -> Iterator[VerifiedPage]:
    """Lazily yield each page of the batch, one GET per FileEntry, in manifest order.

    Raises PayloadIntegrityError (permanent) on missing/corrupt payloads; RawStoreTransientError
    from the store propagates unchanged (retryable).
    """
    for entry in manifest.files:
        try:
            body = store.get(entry.key)
        except RawObjectNotFoundError as exc:
            raise PayloadIntegrityError(f"{entry.key}: payload object is missing") from exc
        rows = _verify(entry, body)
        yield VerifiedPage(entry=entry, body=body, rows=rows)

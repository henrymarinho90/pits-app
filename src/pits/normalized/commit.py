"""Write-once commit of a normalized artifact: objects first, manifest last (commit marker).

Retries and conflicts are handled by put_once (D75): identical bytes are a no-op, different
bytes at the same key raise RawObjectConflictError. Objects above 8 MiB fail permanently.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

from pits.ingestion.raw_store import PutOutcome, RawStore
from pits.normalized.fx_rate_csv import CONTENT_TYPE


class NormalizedOutcome(Enum):
    CREATED = "created"
    ALREADY_PRESENT = "already_present"


def commit_objects(
    store: RawStore,
    objects: Mapping[str, tuple[bytes, str]] | list[tuple[str, bytes, str]],
    manifest_key: str,
    manifest_bytes: bytes,
) -> NormalizedOutcome:
    """put_once every object (key -> (bytes, content_type)), then the manifest as commit marker.

    CREATED if the manifest was written now; ALREADY_PRESENT if identical. A crash in between
    leaves orphan objects; a retry finds them identical and then writes the manifest (CREATED).
    """
    items = (
        [(k, b, ct) for k, (b, ct) in objects.items()]
        if isinstance(objects, Mapping)
        else list(objects)
    )
    keys = [k for k, _, _ in items]
    if not items:
        raise ValueError("commit_objects requires at least one object")
    if len(set(keys)) != len(keys):
        raise ValueError("commit_objects: duplicate object keys")
    if manifest_key in keys:
        raise ValueError("commit_objects: manifest_key must not be among the objects")
    for key, body, content_type in items:
        store.put_once(key, body, content_type)
    outcome = store.put_once(manifest_key, manifest_bytes, "application/json")
    return (
        NormalizedOutcome.CREATED
        if outcome is PutOutcome.CREATED
        else NormalizedOutcome.ALREADY_PRESENT
    )


def commit_normalized(
    store: RawStore,
    *,
    csv_key: str,
    csv_bytes: bytes,
    manifest_key: str,
    manifest_bytes: bytes,
) -> NormalizedOutcome:
    """CREATED if the manifest (commit marker) was written now; ALREADY_PRESENT if identical.

    A crash between the two writes leaves an orphan CSV; a retry finds it identical and then
    writes the manifest, so the outcome of that retry is CREATED.
    """
    return commit_objects(store, [(csv_key, csv_bytes, CONTENT_TYPE)], manifest_key, manifest_bytes)

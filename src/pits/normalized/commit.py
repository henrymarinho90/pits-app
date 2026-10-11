"""Write-once commit of a normalized artifact: CSV first, manifest last (commit marker).

Retries and conflicts are handled by put_once (D75): identical bytes are a no-op, different
bytes at the same key raise RawObjectConflictError. Objects above 8 MiB fail permanently.
"""

from __future__ import annotations

from enum import Enum

from pits.ingestion.raw_store import PutOutcome, RawStore
from pits.normalized.fx_rate_csv import CONTENT_TYPE


class NormalizedOutcome(Enum):
    CREATED = "created"
    ALREADY_PRESENT = "already_present"


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
    store.put_once(csv_key, csv_bytes, CONTENT_TYPE)
    outcome = store.put_once(manifest_key, manifest_bytes, "application/json")
    return (
        NormalizedOutcome.CREATED
        if outcome is PutOutcome.CREATED
        else NormalizedOutcome.ALREADY_PRESENT
    )

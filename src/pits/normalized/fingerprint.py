"""Generic input fingerprint of a normalized artifact (D74/D76, D98): source-agnostic.

Must not import pits.sources.*: any source can build its normalized artifact on top of it.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime


def is_canonical_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


@dataclass(frozen=True)
class Transform:
    name: str
    rules_version: str


@dataclass(frozen=True)
class InputRef:
    batch_id: str
    extraction_date: date
    finished_at: datetime
    mode: str
    manifest_key: str
    manifest_sha256: str


def compute_input_fingerprint(
    transform: Transform, raw_bucket: str, inputs: Sequence[InputRef]
) -> str:
    """sha256 of the canonical JSON of what determines the output (inputs in commit order)."""
    payload = {
        "transform": {"name": transform.name, "rules_version": transform.rules_version},
        "raw_bucket": raw_bucket,
        "inputs": [
            {
                "batch_id": i.batch_id,
                "manifest_key": i.manifest_key,
                "manifest_sha256": i.manifest_sha256,
            }
            for i in inputs
        ],
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

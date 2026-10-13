"""Select and read the committed normalized divipola_municipality artifact (D123, D124).

Layout written by `pits normalize divipola`:
`divipola_municipality/source_system=dane_divipola/rows_updated=YYYY-MM-DD/fingerprint=<sha256>/
{municipality.csv, manifest.json}`. The manifest is the commit marker: a directory without it
(orphan CSV of a crashed write) is ignored. A manifest that cannot be parsed, or whose content
disagrees with its own key, is a permanent error: the loader never guesses.

Selection: among the manifests with the expected transform (name + rules_version) and raw_bucket,
the winner has the greatest commit order of its input (extraction_date, finished_at, batch_id,
D76); two artifacts with the same input but different fingerprints are ambiguous. `fingerprint`
restricts the choice to that artifact (it still has to satisfy the transform/raw_bucket checks).
The CSV (at most 8 MiB) is fetched whole and verified against the manifest before use.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date

from pits.ingestion.manifest import sha256_hex
from pits.ingestion.raw_store import (
    RawObjectNotFoundError,
    RawStore,
    RawStoreError,
    RawStoreTransientError,
)
from pits.normalized.divipola_csv import HEADER_BYTES
from pits.normalized.divipola_manifest import (
    DATASET,
    DIVIPOLA_MANIFEST_NAME,
    DivipolaManifest,
    DivipolaManifestError,
)
from pits.normalized.fingerprint import InputRef
from pits.normalized.reader import (
    CommitOrder,
    NormalizedReadPermanentError,
    NormalizedReadTransientError,
    commit_order,
)
from pits.sources.divipola.contract import SOURCE_SYSTEM
from pits.sources.divipola.normalize import DEFAULT_RULES_VERSION, TRANSFORM_NAME

SOURCE_PREFIX = f"{DATASET}/source_system={SOURCE_SYSTEM}/"

_DATE_DIR_RE = re.compile(r"rows_updated=([0-9]{4}-[0-9]{2}-[0-9]{2})/")
_FINGERPRINT_RE = re.compile(r"fingerprint=([0-9a-f]{64})/")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class SelectedDivipola:
    """A validated, committed artifact (manifest only; the CSV is read later)."""

    manifest: DivipolaManifest
    manifest_key: str
    manifest_sha256: str
    # Stored parsed as jsonb in ops.load_run; manifest_sha256 vouches for the exact bytes.
    manifest_bytes: bytes = field(repr=False)

    @property
    def rows_updated(self) -> date:
        return self.manifest.rows_updated

    @property
    def input_ref(self) -> InputRef:
        return self.manifest.inputs[0]  # the manifest guarantees exactly one input

    @property
    def commit_order(self) -> CommitOrder:
        return commit_order(self.input_ref)

    @property
    def csv_key(self) -> str:
        return self.manifest.output.key


def _permanent(message: str) -> NormalizedReadPermanentError:
    return NormalizedReadPermanentError(message)


def _list(store: RawStore, prefix: str) -> list[str]:
    try:
        return store.list_prefixes(prefix)
    except RawStoreTransientError as exc:
        raise NormalizedReadTransientError(str(exc)) from exc
    except RawStoreError as exc:
        raise _permanent(str(exc)) from exc


def _candidate_dirs(store: RawStore, fingerprint: str | None) -> list[tuple[str, str]]:
    """(rows_updated label, directory) of every `.../rows_updated=X/fingerprint=Y/`."""
    dirs: list[tuple[str, str]] = []
    for date_prefix in _list(store, SOURCE_PREFIX):
        day = _DATE_DIR_RE.fullmatch(date_prefix[len(SOURCE_PREFIX) :])
        if day is None:
            continue  # not a layout directory: ignore unrelated prefixes
        for fp_prefix in _list(store, date_prefix):
            match = _FINGERPRINT_RE.fullmatch(fp_prefix[len(date_prefix) :])
            if match is None:
                continue
            if fingerprint is None or match.group(1) == fingerprint:
                dirs.append((day.group(1), fp_prefix))
    return dirs


def _load_manifest(store: RawStore, directory: str, label: str) -> SelectedDivipola | None:
    """Parse and validate the manifest of one directory; None when it is an orphan."""
    key = directory + DIVIPOLA_MANIFEST_NAME
    try:
        data = store.get(key)
    except RawObjectNotFoundError:
        return None  # CSV without manifest: write never committed
    except RawStoreTransientError as exc:
        raise NormalizedReadTransientError(str(exc)) from exc
    except RawStoreError as exc:
        raise _permanent(str(exc)) from exc
    try:
        manifest = DivipolaManifest.from_json(data)
    except DivipolaManifestError as exc:
        raise _permanent(f"{key}: {exc}") from exc
    # prefix = f(rows_updated, fingerprint): equal to the directory means both match the key.
    if manifest.prefix != directory or manifest.rows_updated.isoformat() != label:
        raise _permanent(f"{key}: content does not match its key")
    return SelectedDivipola(manifest, key, sha256_hex(data), data)


def _eligibility(selected: SelectedDivipola, raw_bucket: str) -> str | None:
    manifest = selected.manifest
    if (manifest.transform.name, manifest.transform.rules_version) != (
        TRANSFORM_NAME,
        DEFAULT_RULES_VERSION,
    ):
        return "transform/rules_version differs from the expected one"
    if manifest.raw_bucket != raw_bucket:
        return "raw_bucket differs from the configured one"
    return None


def select_artifact(
    store: RawStore, raw_bucket: str, *, fingerprint: str | None = None
) -> SelectedDivipola:
    """The artifact to load; raises typed read errors."""
    if fingerprint is not None and not _SHA256_RE.fullmatch(fingerprint):
        raise ValueError("fingerprint must be 64 lowercase hex characters")
    eligible: list[SelectedDivipola] = []
    for label, directory in _candidate_dirs(store, fingerprint):
        selected = _load_manifest(store, directory, label)
        if selected is None:
            continue
        reason = _eligibility(selected, raw_bucket)
        if reason is None:
            eligible.append(selected)
        elif fingerprint is not None:
            raise _permanent(f"Artifact {fingerprint}: {reason}")
    if not eligible:
        if fingerprint is not None:
            raise _permanent(f"No committed normalized artifact with fingerprint {fingerprint}")
        raise _permanent("No committed normalized divipola_municipality artifact found")
    best = max(item.commit_order for item in eligible)
    top = [item for item in eligible if item.commit_order == best]
    if len(top) > 1:
        raise _permanent(
            "Ambiguous divipola_municipality: several artifacts share the latest input "
            "with different fingerprints"
        )
    return top[0]


def read_csv(store: RawStore, selected: SelectedDivipola) -> bytes:
    """GET the CSV and verify length, sha256 and header against the manifest."""
    output = selected.manifest.output
    try:
        data = store.get(output.key)
    except RawStoreTransientError as exc:
        raise NormalizedReadTransientError(str(exc)) from exc
    except RawStoreError as exc:
        raise _permanent(str(exc)) from exc
    if len(data) != output.size_bytes:
        raise _permanent(f"{output.key}: size does not match the manifest")
    if hashlib.sha256(data).hexdigest() != output.sha256:
        raise _permanent(f"{output.key}: sha256 does not match the manifest")
    if not data.startswith(HEADER_BYTES):
        raise _permanent(f"{output.key}: header does not match the expected one")
    return data

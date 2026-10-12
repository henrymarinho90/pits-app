"""Select and read committed normalized vehicle_fleet_snapshot artifacts (D98, D99).

Layout written by `pits normalize runt`:
`vehicle_fleet_snapshot/source_system=<s>/publication_month=YYYY-MM/fingerprint=<sha256>/
{part-00000.csv, ..., manifest.json}`. The manifest is the commit marker: a directory without it
(orphan parts of a crashed write) is ignored. A manifest that cannot be parsed, or whose content
disagrees with its own key, is a permanent error: the loader never guesses.

Selection: one artifact per publication. Among the manifests with the expected transform
(name + rules_version) and raw_bucket, the winner has the greatest commit order of its input
(extraction_date, finished_at, batch_id, D76); two artifacts with the same input but different
fingerprints are ambiguous. `fingerprint` restricts the choice to that artifact (it still has to
satisfy the transform/raw_bucket checks) and `publication` to one month.

Reading is streaming, part by part: each part (at most 8 MiB) is fetched, its size, sha256 and
header are verified against the manifest, and only then handed to the caller.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date

from pits.ingestion.manifest import sha256_hex
from pits.ingestion.raw_store import (
    RawObjectNotFoundError,
    RawStore,
    RawStoreError,
    RawStoreTransientError,
)
from pits.normalized.fingerprint import InputRef
from pits.normalized.fleet_csv import HEADER_BYTES
from pits.normalized.fleet_manifest import (
    DATASET,
    FLEET_MANIFEST_NAME,
    FleetManifest,
    FleetManifestError,
    PartEntry,
)
from pits.normalized.reader import (
    CommitOrder,
    NormalizedReadPermanentError,
    NormalizedReadTransientError,
    commit_order,
)
from pits.sources.runt.contract import SOURCE_SYSTEM
from pits.sources.runt.normalize import DEFAULT_RULES_VERSION, TRANSFORM_NAME

SOURCE_PREFIX = f"{DATASET}/source_system={SOURCE_SYSTEM}/"

PUBLICATION_RE = re.compile(r"20[0-9]{2}-(?:0[1-9]|1[0-2])")
_PUBLICATION_DIR_RE = re.compile(r"publication_month=([0-9]{4}-[0-9]{2})/")
_FINGERPRINT_RE = re.compile(r"fingerprint=([0-9a-f]{64})/")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class SelectedFleetArtifact:
    """A validated, committed artifact (manifest only; the parts are read later)."""

    manifest: FleetManifest
    manifest_key: str
    manifest_sha256: str
    # Stored parsed as jsonb in ops.load_run; manifest_sha256 vouches for the exact bytes.
    manifest_bytes: bytes = field(repr=False)

    @property
    def publication(self) -> str:
        return self.manifest.publication.label

    @property
    def input_ref(self) -> InputRef:
        return self.manifest.inputs[0]  # the manifest guarantees exactly one input

    @property
    def commit_order(self) -> CommitOrder:
        return commit_order(self.input_ref)

    @property
    def prefix(self) -> str:
        return self.manifest.prefix

    @property
    def publication_first_day(self) -> date:
        return date(self.manifest.publication.year, self.manifest.publication.month, 1)


def _permanent(message: str) -> NormalizedReadPermanentError:
    return NormalizedReadPermanentError(message)


def _list(store: RawStore, prefix: str) -> list[str]:
    try:
        return store.list_prefixes(prefix)
    except RawStoreTransientError as exc:
        raise NormalizedReadTransientError(str(exc)) from exc
    except RawStoreError as exc:
        raise _permanent(str(exc)) from exc


def _candidate_dirs(
    store: RawStore, publication: str | None, fingerprint: str | None
) -> list[tuple[str, str]]:
    """(publication label, directory) of every `.../publication_month=X/fingerprint=Y/`."""
    dirs: list[tuple[str, str]] = []
    for month_prefix in _list(store, SOURCE_PREFIX):
        month = _PUBLICATION_DIR_RE.fullmatch(month_prefix[len(SOURCE_PREFIX) :])
        if month is None:
            continue  # not a layout directory: ignore unrelated prefixes
        if publication is not None and month.group(1) != publication:
            continue
        for fp_prefix in _list(store, month_prefix):
            match = _FINGERPRINT_RE.fullmatch(fp_prefix[len(month_prefix) :])
            if match is None:
                continue
            if fingerprint is None or match.group(1) == fingerprint:
                dirs.append((month.group(1), fp_prefix))
    return dirs


def _load_manifest(store: RawStore, directory: str, label: str) -> SelectedFleetArtifact | None:
    """Parse and validate the manifest of one directory; None when it is an orphan."""
    key = directory + FLEET_MANIFEST_NAME
    try:
        data = store.get(key)
    except RawObjectNotFoundError:
        return None  # parts without manifest: write never committed
    except RawStoreTransientError as exc:
        raise NormalizedReadTransientError(str(exc)) from exc
    except RawStoreError as exc:
        raise _permanent(str(exc)) from exc
    try:
        manifest = FleetManifest.from_json(data)
    except FleetManifestError as exc:
        raise _permanent(f"{key}: {exc}") from exc
    # prefix = f(publication, fingerprint): equal to the directory means both match the key.
    if manifest.prefix != directory or manifest.publication.label != label:
        raise _permanent(f"{key}: content does not match its key")
    return SelectedFleetArtifact(manifest, key, sha256_hex(data), data)


def _eligibility(selected: SelectedFleetArtifact, raw_bucket: str) -> str | None:
    """Reason why the artifact is not eligible, or None."""
    manifest = selected.manifest
    if (manifest.transform.name, manifest.transform.rules_version) != (
        TRANSFORM_NAME,
        DEFAULT_RULES_VERSION,
    ):
        return "transform/rules_version differs from the expected one"
    if manifest.raw_bucket != raw_bucket:
        return "raw_bucket differs from the configured one"
    if manifest.row_count <= 0:
        return "row_count is 0"
    return None


def select_artifacts(
    store: RawStore,
    raw_bucket: str,
    *,
    publication: str | None = None,
    fingerprint: str | None = None,
) -> list[SelectedFleetArtifact]:
    """One artifact per publication, ascending by publication; raises typed read errors."""
    if publication is not None and not PUBLICATION_RE.fullmatch(publication):
        raise ValueError("publication must be YYYY-MM")
    if fingerprint is not None and not _SHA256_RE.fullmatch(fingerprint):
        raise ValueError("fingerprint must be 64 lowercase hex characters")
    eligible: dict[str, list[SelectedFleetArtifact]] = {}
    for label, directory in _candidate_dirs(store, publication, fingerprint):
        selected = _load_manifest(store, directory, label)
        if selected is None:
            continue
        reason = _eligibility(selected, raw_bucket)
        if reason is None:
            eligible.setdefault(label, []).append(selected)
        elif fingerprint is not None:
            raise _permanent(f"Artifact {fingerprint}: {reason}")
    if not eligible:
        if fingerprint is not None:
            raise _permanent(f"No committed normalized artifact with fingerprint {fingerprint}")
        scope = f" for publication {publication}" if publication else ""
        raise _permanent(f"No committed normalized vehicle_fleet_snapshot artifact found{scope}")
    winners: list[SelectedFleetArtifact] = []
    for label in sorted(eligible):
        items = eligible[label]
        best = max(item.commit_order for item in items)
        top = [item for item in items if item.commit_order == best]
        if len(top) > 1:
            raise _permanent(
                f"Ambiguous publication {label}: several artifacts share the latest input "
                "with different fingerprints"
            )
        winners.append(top[0])
    return winners


def read_part(store: RawStore, part: PartEntry) -> bytes:
    """GET one part and verify length, sha256 and header against the manifest."""
    try:
        data = store.get(part.key)
    except RawStoreTransientError as exc:
        raise NormalizedReadTransientError(str(exc)) from exc
    except RawStoreError as exc:
        raise _permanent(str(exc)) from exc
    if len(data) != part.size_bytes:
        raise _permanent(f"{part.key}: size does not match the manifest")
    if hashlib.sha256(data).hexdigest() != part.sha256:
        raise _permanent(f"{part.key}: sha256 does not match the manifest")
    if not data.startswith(HEADER_BYTES):
        raise _permanent(f"{part.key}: header does not match the expected one")
    return data


def iter_parts(
    store: RawStore, selected: SelectedFleetArtifact
) -> Iterator[tuple[PartEntry, bytes]]:
    """Yield (entry, verified bytes) part by part, in order; one part in memory at a time."""
    for part in selected.manifest.parts:
        yield part, read_part(store, part)

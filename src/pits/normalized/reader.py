"""Select and read a committed normalized fx_rate artifact (D76, D82 step 1).

Layout written by the normalizer (`pits.sources.trm.normalize`):
`fx_rate/source_system=<s>/inputs_until=<YYYY-MM-DD>/fingerprint=<sha256>/{fx_rate.csv,manifest.json}`.
The manifest is the commit marker: a directory without it (orphan CSV from a crashed write) is
ignored. A manifest that cannot be parsed, or whose content disagrees with its own key, is a
permanent error: the loader never guesses.

Selection (D76 a): among manifests with the expected transform (name + rules_version) and
raw_bucket, the winner has the greatest commit order of its LAST input
(extraction_date, finished_at, batch_id). Two artifacts with the same last input but different
fingerprints are ambiguous -> permanent error. `fingerprint` forces one artifact (it still has
to satisfy the transform/raw_bucket checks).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime

from pits.ingestion.manifest import sha256_hex
from pits.ingestion.raw_store import (
    RawObjectNotFoundError,
    RawStore,
    RawStoreError,
    RawStoreTransientError,
)
from pits.normalized.manifest import (
    NORMALIZED_MANIFEST_NAME,
    InputRef,
    NormalizedManifest,
    NormalizedManifestError,
)
from pits.sources.trm.contract import BACKFILL_FROM, SOURCE_SYSTEM
from pits.sources.trm.normalize import DEFAULT_RULES_VERSION, TRANSFORM_NAME

DATASET = "fx_rate"
CSV_NAME = "fx_rate.csv"
SOURCE_PREFIX = f"{DATASET}/source_system={SOURCE_SYSTEM}/"

_UNTIL_RE = re.compile(r"inputs_until=(\d{4}-\d{2}-\d{2})/")
_FINGERPRINT_RE = re.compile(r"fingerprint=([0-9a-f]{64})/")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")

CommitOrder = tuple[date, datetime, str]


class NormalizedReadError(RuntimeError):
    """Base class of reader failures; messages never contain credentials."""


class NormalizedReadPermanentError(NormalizedReadError):
    """Retrying cannot help (corrupt/inconsistent artifact, ambiguity, hash mismatch)."""


class NormalizedReadTransientError(NormalizedReadError):
    """Store/network failure: the same command may succeed later."""


@dataclass(frozen=True)
class SelectedArtifact:
    manifest: NormalizedManifest
    manifest_key: str
    manifest_sha256: str
    csv_key: str

    @property
    def last_input(self) -> InputRef:
        return last_input(self.manifest)

    @property
    def commit_order(self) -> CommitOrder:
        return commit_order(self.last_input)


@dataclass(frozen=True)
class FxRateArtifact:
    """A selected artifact plus its verified CSV bytes, with the load_run metadata."""

    selected: SelectedArtifact
    csv_bytes: bytes

    @property
    def manifest(self) -> NormalizedManifest:
        return self.selected.manifest

    @property
    def manifest_key(self) -> str:
        return self.selected.manifest_key

    @property
    def manifest_sha256(self) -> str:
        return self.selected.manifest_sha256

    @property
    def csv_key(self) -> str:
        return self.selected.csv_key

    @property
    def csv_sha256(self) -> str:
        return self.manifest.output.sha256

    @property
    def csv_size_bytes(self) -> int:
        return self.manifest.output.size_bytes

    @property
    def fingerprint(self) -> str:
        return self.manifest.input_fingerprint

    @property
    def transform_name(self) -> str:
        return self.manifest.transform.name

    @property
    def rules_version(self) -> str:
        return self.manifest.transform.rules_version

    @property
    def row_count(self) -> int:
        return self.manifest.row_count

    @property
    def coverage_from(self) -> date:
        return self.manifest.coverage.from_date

    @property
    def coverage_to(self) -> date:
        return self.manifest.coverage.to_date

    @property
    def last_input(self) -> InputRef:
        return self.selected.last_input

    @property
    def last_input_batch_id(self) -> str:
        return self.last_input.batch_id

    @property
    def last_input_extraction_date(self) -> date:
        return self.last_input.extraction_date

    @property
    def last_input_finished_at(self) -> datetime:
        return self.last_input.finished_at


def commit_order(ref: InputRef) -> CommitOrder:
    return (ref.extraction_date, ref.finished_at, ref.batch_id)


def last_input(manifest: NormalizedManifest) -> InputRef:
    """The input with the greatest commit order (the normalizer lists inputs in that order)."""
    return max(manifest.inputs, key=commit_order)


def _permanent(message: str) -> NormalizedReadPermanentError:
    return NormalizedReadPermanentError(message)


def _list(store: RawStore, prefix: str) -> list[str]:
    try:
        return store.list_prefixes(prefix)
    except RawStoreTransientError as exc:
        raise NormalizedReadTransientError(str(exc)) from exc
    except RawStoreError as exc:
        raise _permanent(str(exc)) from exc


def _candidate_dirs(store: RawStore, fingerprint: str | None) -> list[str]:
    """Directories `.../inputs_until=X/fingerprint=Y/` under the source prefix."""
    dirs: list[str] = []
    for until_prefix in _list(store, SOURCE_PREFIX):
        if not _UNTIL_RE.fullmatch(until_prefix[len(SOURCE_PREFIX) :]):
            continue  # not a layout directory: ignore unrelated prefixes
        for fp_prefix in _list(store, until_prefix):
            match = _FINGERPRINT_RE.fullmatch(fp_prefix[len(until_prefix) :])
            if match is None:
                continue
            if fingerprint is None or match.group(1) == fingerprint:
                dirs.append(fp_prefix)
    return dirs


def _load_manifest(store: RawStore, directory: str) -> SelectedArtifact | None:
    """Parse and validate the manifest of one directory; None when it is an orphan."""
    key = directory + NORMALIZED_MANIFEST_NAME
    try:
        data = store.get(key)
    except RawObjectNotFoundError:
        return None  # CSV without manifest: write never committed
    except RawStoreTransientError as exc:
        raise NormalizedReadTransientError(str(exc)) from exc
    except RawStoreError as exc:
        raise _permanent(str(exc)) from exc
    try:
        manifest = NormalizedManifest.from_json(data)
    except NormalizedManifestError as exc:
        raise _permanent(f"{key}: {exc}") from exc

    until = _UNTIL_RE.search(directory)
    fingerprint = _FINGERPRINT_RE.search(directory)
    assert until is not None and fingerprint is not None  # guaranteed by _candidate_dirs
    if manifest.input_fingerprint != fingerprint.group(1):
        raise _permanent(f"{key}: input_fingerprint does not match its key")
    if last_input(manifest).extraction_date.isoformat() != until.group(1):
        raise _permanent(f"{key}: inputs_until does not match the last input")
    csv_key = directory + CSV_NAME
    if manifest.output.key != csv_key:
        raise _permanent(f"{key}: output.key does not match its key")
    return SelectedArtifact(manifest, key, sha256_hex(data), csv_key)


def _check_expected(selected: SelectedArtifact, raw_bucket: str) -> str | None:
    """Reason why the artifact is not eligible, or None."""
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
    store: RawStore, raw_bucket: str, fingerprint: str | None = None
) -> SelectedArtifact:
    """Pick the artifact to load (see module docstring); raises typed read errors."""
    if fingerprint is not None and not _SHA256_RE.fullmatch(fingerprint):
        raise ValueError("fingerprint must be 64 lowercase hex characters")
    eligible: list[SelectedArtifact] = []
    for directory in _candidate_dirs(store, fingerprint):
        selected = _load_manifest(store, directory)
        if selected is None:
            continue
        reason = _check_expected(selected, raw_bucket)
        if reason is None:
            eligible.append(selected)
        elif fingerprint is not None:
            raise _permanent(f"Artifact {fingerprint}: {reason}")
    if not eligible:
        if fingerprint is not None:
            raise _permanent(f"No committed normalized artifact with fingerprint {fingerprint}")
        raise _permanent("No committed normalized fx_rate artifact found")
    best = max(item.commit_order for item in eligible)
    winners = [item for item in eligible if item.commit_order == best]
    if len(winners) > 1:
        raise _permanent(
            "Ambiguous: several artifacts share the latest input with different fingerprints"
        )
    return winners[0]


def read_artifact(store: RawStore, selected: SelectedArtifact) -> FxRateArtifact:
    """Apply the loader guards, GET the CSV and verify length and sha256 against the manifest."""
    manifest = selected.manifest
    if manifest.row_count <= 0:
        raise _permanent("Artifact has row_count == 0")
    if manifest.coverage.from_date != BACKFILL_FROM:
        raise _permanent(
            f"coverage.from is {manifest.coverage.from_date.isoformat()}, "
            f"expected {BACKFILL_FROM.isoformat()}"
        )
    try:
        data = store.get(selected.csv_key)
    except RawStoreTransientError as exc:
        raise NormalizedReadTransientError(str(exc)) from exc
    except RawStoreError as exc:
        raise _permanent(str(exc)) from exc
    if len(data) != manifest.output.size_bytes:
        raise _permanent(f"{selected.csv_key}: size does not match the manifest")
    if hashlib.sha256(data).hexdigest() != manifest.output.sha256:
        raise _permanent(f"{selected.csv_key}: sha256 does not match the manifest")
    return FxRateArtifact(selected, data)


def load_artifact(
    store: RawStore, raw_bucket: str, fingerprint: str | None = None
) -> FxRateArtifact:
    """select_artifact + read_artifact."""
    return read_artifact(store, select_artifact(store, raw_bucket, fingerprint))

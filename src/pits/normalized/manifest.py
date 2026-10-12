"""Normalized manifest v1 (D76 e): the commit marker of a normalized artifact.

Deterministic by construction: no execution timestamp, no uuid, no package version.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date

from pits.ingestion import strict_json as sj
from pits.ingestion.manifest import WATERMARK_MODES
from pits.normalized.fingerprint import (  # noqa: F401  (re-exported: legacy import path)
    InputRef,
    Transform,
    compute_input_fingerprint,
    is_canonical_uuid,
)
from pits.sources.trm.contract import DATASET_ID, SOURCE_SYSTEM

NORMALIZED_MANIFEST_VERSION = 1
NORMALIZED_MANIFEST_NAME = "manifest.json"
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class NormalizedManifestError(ValueError):
    """The normalized manifest is invalid or corrupt (permanent)."""


@dataclass(frozen=True)
class Coverage:
    from_date: date
    to_date: date


@dataclass(frozen=True)
class Output:
    key: str
    sha256: str
    size_bytes: int
    content_type: str


@dataclass(frozen=True)
class NormalizedManifest:
    source_system: str
    dataset_id: str
    transform: Transform
    raw_bucket: str
    inputs: tuple[InputRef, ...]
    baseline_batch_id: str
    input_fingerprint: str
    coverage: Coverage
    row_count: int
    max_range_days: int
    output: Output
    dataset: str = "fx_rate"
    manifest_version: int = NORMALIZED_MANIFEST_VERSION

    def __post_init__(self) -> None:
        if self.manifest_version != NORMALIZED_MANIFEST_VERSION:
            raise NormalizedManifestError(
                f"Unsupported manifest_version: {self.manifest_version!r}"
            )
        if self.dataset != "fx_rate":
            raise NormalizedManifestError(f"Unexpected dataset: {self.dataset!r}")
        if not self.inputs:
            raise NormalizedManifestError("inputs must not be empty")
        if self.baseline_batch_id not in {i.batch_id for i in self.inputs}:
            raise NormalizedManifestError("baseline_batch_id is not among the inputs")
        if (self.source_system, self.dataset_id) != (SOURCE_SYSTEM, DATASET_ID):
            raise NormalizedManifestError(
                f"Unexpected source: {self.source_system!r}/{self.dataset_id!r}"
            )
        for i in self.inputs:
            if i.mode not in WATERMARK_MODES:
                raise NormalizedManifestError(f"Invalid input mode: {i.mode!r}")
            if not is_canonical_uuid(i.batch_id):
                raise NormalizedManifestError(f"Invalid input batch_id: {i.batch_id!r}")
            if not _SHA256_RE.fullmatch(i.manifest_sha256):
                raise NormalizedManifestError(f"Invalid manifest_sha256 for {i.batch_id}")
            if i.finished_at.tzinfo is None or i.finished_at.utcoffset() is None:
                raise NormalizedManifestError("inputs.finished_at must be timezone-aware")
        if not is_canonical_uuid(self.baseline_batch_id):
            raise NormalizedManifestError("Invalid baseline_batch_id")
        if not (
            self.output.key.startswith("fx_rate/")
            and f"/fingerprint={self.input_fingerprint}/" in self.output.key
        ):
            raise NormalizedManifestError("output.key is not under this input_fingerprint")
        if not _SHA256_RE.fullmatch(self.output.sha256):
            raise NormalizedManifestError("Invalid output.sha256")
        if min(self.row_count, self.max_range_days, self.output.size_bytes) < 0:
            raise NormalizedManifestError("Negative number in manifest")
        if self.coverage.to_date < self.coverage.from_date:
            raise NormalizedManifestError("coverage.to is before coverage.from")
        expected = compute_input_fingerprint(self.transform, self.raw_bucket, self.inputs)
        if self.input_fingerprint != expected:
            raise NormalizedManifestError("input_fingerprint does not match the inputs")

    def to_json(self) -> bytes:
        """Deterministic UTF-8 JSON: indent=2, sorted keys, LF, trailing newline."""
        text = json.dumps(
            _to_dict(self), sort_keys=True, ensure_ascii=False, indent=2, separators=(",", ": ")
        )
        return (text + "\n").encode("utf-8")

    @classmethod
    def from_json(cls, data: bytes) -> NormalizedManifest:
        """Strictly parse: exact keys and types, version and fingerprint consistency."""
        try:
            raw = json.loads(data.decode("utf-8"))
            return _from_dict(raw)
        except (UnicodeDecodeError, ValueError) as exc:
            if isinstance(exc, NormalizedManifestError):
                raise
            raise NormalizedManifestError(f"Invalid normalized manifest: {exc}") from exc


def _to_dict(m: NormalizedManifest) -> dict[str, object]:
    return {
        "manifest_version": m.manifest_version,
        "dataset": m.dataset,
        "source_system": m.source_system,
        "dataset_id": m.dataset_id,
        "transform": {"name": m.transform.name, "rules_version": m.transform.rules_version},
        "raw_bucket": m.raw_bucket,
        "inputs": [
            {
                "batch_id": i.batch_id,
                "extraction_date": i.extraction_date.isoformat(),
                "finished_at": sj.format_datetime(i.finished_at),
                "mode": i.mode,
                "manifest_key": i.manifest_key,
                "manifest_sha256": i.manifest_sha256,
            }
            for i in m.inputs
        ],
        "baseline_batch_id": m.baseline_batch_id,
        "input_fingerprint": m.input_fingerprint,
        "coverage": {
            "from": m.coverage.from_date.isoformat(),
            "to": m.coverage.to_date.isoformat(),
        },
        "row_count": m.row_count,
        "max_range_days": m.max_range_days,
        "output": {
            "key": m.output.key,
            "sha256": m.output.sha256,
            "size_bytes": m.output.size_bytes,
            "content_type": m.output.content_type,
        },
    }


def _from_dict(raw: object) -> NormalizedManifest:
    try:
        top = sj.obj(
            raw,
            {
                "manifest_version",
                "dataset",
                "source_system",
                "dataset_id",
                "transform",
                "raw_bucket",
                "inputs",
                "baseline_batch_id",
                "input_fingerprint",
                "coverage",
                "row_count",
                "max_range_days",
                "output",
            },
            "manifest",
        )
        transform = sj.obj(top["transform"], {"name", "rules_version"}, "transform")
        coverage = sj.obj(top["coverage"], {"from", "to"}, "coverage")
        output = sj.obj(top["output"], {"key", "sha256", "size_bytes", "content_type"}, "output")
        inputs = []
        for n, item in enumerate(sj.array(top["inputs"], "inputs")):
            i = sj.obj(
                item,
                {
                    "batch_id",
                    "extraction_date",
                    "finished_at",
                    "mode",
                    "manifest_key",
                    "manifest_sha256",
                },
                f"inputs[{n}]",
            )
            inputs.append(
                InputRef(
                    batch_id=sj.string(i["batch_id"], f"inputs[{n}].batch_id"),
                    extraction_date=sj.iso_date(
                        i["extraction_date"], f"inputs[{n}].extraction_date"
                    ),
                    finished_at=sj.utc_datetime(i["finished_at"], f"inputs[{n}].finished_at"),
                    mode=sj.string(i["mode"], f"inputs[{n}].mode"),
                    manifest_key=sj.string(i["manifest_key"], f"inputs[{n}].manifest_key"),
                    manifest_sha256=sj.string(i["manifest_sha256"], f"inputs[{n}].manifest_sha256"),
                )
            )
        version = sj.integer(top["manifest_version"], "manifest_version")
        return NormalizedManifest(
            manifest_version=version,
            dataset=sj.string(top["dataset"], "dataset"),
            source_system=sj.string(top["source_system"], "source_system"),
            dataset_id=sj.string(top["dataset_id"], "dataset_id"),
            transform=Transform(
                sj.string(transform["name"], "transform.name"),
                sj.string(transform["rules_version"], "transform.rules_version"),
            ),
            raw_bucket=sj.string(top["raw_bucket"], "raw_bucket"),
            inputs=tuple(inputs),
            baseline_batch_id=sj.string(top["baseline_batch_id"], "baseline_batch_id"),
            input_fingerprint=sj.string(top["input_fingerprint"], "input_fingerprint"),
            coverage=Coverage(
                sj.iso_date(coverage["from"], "coverage.from"),
                sj.iso_date(coverage["to"], "coverage.to"),
            ),
            row_count=sj.integer(top["row_count"], "row_count"),
            max_range_days=sj.integer(top["max_range_days"], "max_range_days"),
            output=Output(
                key=sj.string(output["key"], "output.key"),
                sha256=sj.string(output["sha256"], "output.sha256"),
                size_bytes=sj.integer(output["size_bytes"], "output.size_bytes"),
                content_type=sj.string(output["content_type"], "output.content_type"),
            ),
        )
    except sj.StrictJsonError as exc:
        raise NormalizedManifestError(str(exc)) from exc

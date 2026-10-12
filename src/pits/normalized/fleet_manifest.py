"""Normalized manifest v1 of vehicle_fleet_snapshot (D98): the commit marker of a publication.

Same style as the fx_rate manifest (normalized.manifest): deterministic JSON (sorted keys,
UTF-8, LF), no execution timestamp, no uuid, no package version. The manifest lists the CSV
parts and describes the logical CSV (header once, then every row) with content_sha256 and
content_size_bytes. `input_fingerprint` is D76(e) over the single winning raw batch.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from pits.ingestion import strict_json as sj
from pits.ingestion.manifest import WATERMARK_MODES
from pits.normalized.fingerprint import (
    InputRef,
    Transform,
    compute_input_fingerprint,
    is_canonical_uuid,
)
from pits.normalized.fleet_csv import (
    CONTENT_TYPE,
    HEADER,
    HEADER_BYTES,
    MAX_PART_BYTES,
    MAX_PART_ROWS,
    part_name,
)
from pits.sources.runt.contract import DATASET_ID, SOURCE_SYSTEM

DATASET = "vehicle_fleet_snapshot"
FLEET_MANIFEST_VERSION = 1
FLEET_MANIFEST_NAME = "manifest.json"
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class FleetManifestError(ValueError):
    """The fleet manifest is invalid or corrupt (permanent)."""


def artifact_prefix(publication: str, fingerprint: str) -> str:
    """'vehicle_fleet_snapshot/source_system=<s>/publication_month=YYYY-MM/fingerprint=<fp>/'."""
    return (
        f"{DATASET}/source_system={SOURCE_SYSTEM}/"
        f"publication_month={publication}/fingerprint={fingerprint}/"
    )


@dataclass(frozen=True)
class Publication:
    year: int
    month: int

    @property
    def label(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


@dataclass(frozen=True)
class PartEntry:
    key: str
    sha256: str
    size_bytes: int
    row_count: int


@dataclass(frozen=True)
class FleetManifest:
    source_system: str
    dataset_id: str
    transform: Transform
    raw_bucket: str
    inputs: tuple[InputRef, ...]
    input_fingerprint: str
    publication: Publication
    row_count: int
    vehicle_count_total: int
    content_sha256: str
    content_size_bytes: int
    parts: tuple[PartEntry, ...]
    dataset: str = DATASET
    content_type: str = CONTENT_TYPE
    header: str = HEADER
    manifest_version: int = FLEET_MANIFEST_VERSION

    def __post_init__(self) -> None:
        if self.manifest_version != FLEET_MANIFEST_VERSION:
            raise FleetManifestError(f"Unsupported manifest_version: {self.manifest_version!r}")
        if self.dataset != DATASET:
            raise FleetManifestError(f"Unexpected dataset: {self.dataset!r}")
        if (self.source_system, self.dataset_id) != (SOURCE_SYSTEM, DATASET_ID):
            raise FleetManifestError(
                f"Unexpected source: {self.source_system!r}/{self.dataset_id!r}"
            )
        if (self.content_type, self.header) != (CONTENT_TYPE, HEADER):
            raise FleetManifestError("Unexpected content_type or header")
        if len(self.inputs) != 1:
            raise FleetManifestError("inputs must contain exactly one batch")
        for i in self.inputs:
            if i.mode not in WATERMARK_MODES:
                raise FleetManifestError(f"Invalid input mode: {i.mode!r}")
            if not is_canonical_uuid(i.batch_id):
                raise FleetManifestError(f"Invalid input batch_id: {i.batch_id!r}")
            if not _SHA256_RE.fullmatch(i.manifest_sha256):
                raise FleetManifestError(f"Invalid manifest_sha256 for {i.batch_id}")
            if i.finished_at.tzinfo is None or i.finished_at.utcoffset() is None:
                raise FleetManifestError("inputs.finished_at must be timezone-aware")
        if not 1 <= self.publication.month <= 12:
            raise FleetManifestError("publication.month must be 1..12")
        if not _SHA256_RE.fullmatch(self.input_fingerprint):
            raise FleetManifestError("Invalid input_fingerprint")
        expected = compute_input_fingerprint(self.transform, self.raw_bucket, self.inputs)
        if self.input_fingerprint != expected:
            raise FleetManifestError("input_fingerprint does not match the inputs")
        if not _SHA256_RE.fullmatch(self.content_sha256):
            raise FleetManifestError("Invalid content_sha256")
        if min(self.row_count, self.vehicle_count_total, self.content_size_bytes) < 0:
            raise FleetManifestError("Negative number in manifest")
        self._check_parts()

    def _check_parts(self) -> None:
        if not self.parts:
            raise FleetManifestError("parts must not be empty")
        prefix = artifact_prefix(self.publication.label, self.input_fingerprint)
        for n, part in enumerate(self.parts):
            if part.key != prefix + part_name(n):
                raise FleetManifestError(f"parts[{n}].key is not the expected part key")
            if not _SHA256_RE.fullmatch(part.sha256):
                raise FleetManifestError(f"Invalid sha256 for parts[{n}]")
            if not 1 <= part.row_count <= MAX_PART_ROWS:
                raise FleetManifestError(f"parts[{n}].row_count is outside 1..{MAX_PART_ROWS}")
            if not len(HEADER_BYTES) < part.size_bytes <= MAX_PART_BYTES:
                raise FleetManifestError(f"parts[{n}].size_bytes is outside the allowed range")
        if self.row_count != sum(p.row_count for p in self.parts):
            raise FleetManifestError("row_count does not match the sum of parts.row_count")
        logical = len(HEADER_BYTES) + sum(p.size_bytes - len(HEADER_BYTES) for p in self.parts)
        if self.content_size_bytes != logical:
            raise FleetManifestError("content_size_bytes does not match the parts")

    @property
    def prefix(self) -> str:
        return artifact_prefix(self.publication.label, self.input_fingerprint)

    @property
    def manifest_key(self) -> str:
        return self.prefix + FLEET_MANIFEST_NAME

    def to_json(self) -> bytes:
        """Deterministic UTF-8 JSON: indent=2, sorted keys, LF, trailing newline."""
        text = json.dumps(
            _to_dict(self), sort_keys=True, ensure_ascii=False, indent=2, separators=(",", ": ")
        )
        return (text + "\n").encode("utf-8")

    @classmethod
    def from_json(cls, data: bytes) -> FleetManifest:
        """Strictly parse: exact keys and types, version and fingerprint consistency."""
        try:
            return _from_dict(json.loads(data.decode("utf-8")))
        except (UnicodeDecodeError, ValueError) as exc:
            if isinstance(exc, FleetManifestError):
                raise
            raise FleetManifestError(f"Invalid fleet manifest: {exc}") from exc


def _to_dict(m: FleetManifest) -> dict[str, object]:
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
        "input_fingerprint": m.input_fingerprint,
        "publication": {"year": m.publication.year, "month": m.publication.month},
        "row_count": m.row_count,
        "vehicle_count_total": m.vehicle_count_total,
        "content_type": m.content_type,
        "header": m.header,
        "content_sha256": m.content_sha256,
        "content_size_bytes": m.content_size_bytes,
        "parts": [
            {
                "key": p.key,
                "sha256": p.sha256,
                "size_bytes": p.size_bytes,
                "row_count": p.row_count,
            }
            for p in m.parts
        ],
    }


def _from_dict(raw: object) -> FleetManifest:
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
                "input_fingerprint",
                "publication",
                "row_count",
                "vehicle_count_total",
                "content_type",
                "header",
                "content_sha256",
                "content_size_bytes",
                "parts",
            },
            "manifest",
        )
        transform = sj.obj(top["transform"], {"name", "rules_version"}, "transform")
        publication = sj.obj(top["publication"], {"year", "month"}, "publication")
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
        parts = []
        for n, item in enumerate(sj.array(top["parts"], "parts")):
            p = sj.obj(item, {"key", "sha256", "size_bytes", "row_count"}, f"parts[{n}]")
            parts.append(
                PartEntry(
                    key=sj.string(p["key"], f"parts[{n}].key"),
                    sha256=sj.string(p["sha256"], f"parts[{n}].sha256"),
                    size_bytes=sj.integer(p["size_bytes"], f"parts[{n}].size_bytes"),
                    row_count=sj.integer(p["row_count"], f"parts[{n}].row_count"),
                )
            )
        return FleetManifest(
            manifest_version=sj.integer(top["manifest_version"], "manifest_version"),
            dataset=sj.string(top["dataset"], "dataset"),
            source_system=sj.string(top["source_system"], "source_system"),
            dataset_id=sj.string(top["dataset_id"], "dataset_id"),
            transform=Transform(
                sj.string(transform["name"], "transform.name"),
                sj.string(transform["rules_version"], "transform.rules_version"),
            ),
            raw_bucket=sj.string(top["raw_bucket"], "raw_bucket"),
            inputs=tuple(inputs),
            input_fingerprint=sj.string(top["input_fingerprint"], "input_fingerprint"),
            publication=Publication(
                sj.integer(publication["year"], "publication.year"),
                sj.integer(publication["month"], "publication.month"),
            ),
            row_count=sj.integer(top["row_count"], "row_count"),
            vehicle_count_total=sj.integer(top["vehicle_count_total"], "vehicle_count_total"),
            content_type=sj.string(top["content_type"], "content_type"),
            header=sj.string(top["header"], "header"),
            content_sha256=sj.string(top["content_sha256"], "content_sha256"),
            content_size_bytes=sj.integer(top["content_size_bytes"], "content_size_bytes"),
            parts=tuple(parts),
        )
    except sj.StrictJsonError as exc:
        raise FleetManifestError(str(exc)) from exc

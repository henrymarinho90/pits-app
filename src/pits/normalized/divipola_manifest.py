"""Normalized manifest v1 of divipola_municipality (D123): the commit marker of the artifact.

Same style as the fx_rate and fleet manifests: deterministic JSON (sorted keys, UTF-8, LF), no
execution timestamp, no uuid, no package version. `input_fingerprint` is D76(e) over the single
winning raw batch. The artifact is one CSV object; the manifest describes it with sha256/size.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date

from pits.ingestion import strict_json as sj
from pits.ingestion.manifest import WATERMARK_MODES
from pits.normalized.divipola_csv import CONTENT_TYPE, CSV_NAME, HEADER
from pits.normalized.fingerprint import (
    InputRef,
    Transform,
    compute_input_fingerprint,
    is_canonical_uuid,
)
from pits.normalized.manifest import Output
from pits.sources.divipola.contract import DATASET_ID, SOURCE_SYSTEM

DATASET = "divipola_municipality"
DIVIPOLA_MANIFEST_VERSION = 1
DIVIPOLA_MANIFEST_NAME = "manifest.json"
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class DivipolaManifestError(ValueError):
    """The divipola manifest is invalid or corrupt (permanent)."""


def artifact_prefix(rows_updated: date, fingerprint: str) -> str:
    """'divipola_municipality/source_system=<s>/rows_updated=YYYY-MM-DD/fingerprint=<fp>/'."""
    return (
        f"{DATASET}/source_system={SOURCE_SYSTEM}/"
        f"rows_updated={rows_updated.isoformat()}/fingerprint={fingerprint}/"
    )


@dataclass(frozen=True)
class DivipolaManifest:
    source_system: str
    dataset_id: str
    transform: Transform
    raw_bucket: str
    inputs: tuple[InputRef, ...]
    input_fingerprint: str
    rows_updated: date  # UTC date of the source rowsUpdatedAt (raw watermark.to_observed)
    row_count: int
    output: Output
    dataset: str = DATASET
    header: str = HEADER
    manifest_version: int = DIVIPOLA_MANIFEST_VERSION

    def __post_init__(self) -> None:
        if self.manifest_version != DIVIPOLA_MANIFEST_VERSION:
            raise DivipolaManifestError(f"Unsupported manifest_version: {self.manifest_version!r}")
        if self.dataset != DATASET:
            raise DivipolaManifestError(f"Unexpected dataset: {self.dataset!r}")
        if (self.source_system, self.dataset_id) != (SOURCE_SYSTEM, DATASET_ID):
            raise DivipolaManifestError(
                f"Unexpected source: {self.source_system!r}/{self.dataset_id!r}"
            )
        if self.header != HEADER:
            raise DivipolaManifestError("Unexpected header")
        if len(self.inputs) != 1:
            raise DivipolaManifestError("inputs must contain exactly one batch")
        for i in self.inputs:
            if i.mode not in WATERMARK_MODES:
                raise DivipolaManifestError(f"Invalid input mode: {i.mode!r}")
            if not is_canonical_uuid(i.batch_id):
                raise DivipolaManifestError(f"Invalid input batch_id: {i.batch_id!r}")
            if not _SHA256_RE.fullmatch(i.manifest_sha256):
                raise DivipolaManifestError(f"Invalid manifest_sha256 for {i.batch_id}")
            if i.finished_at.tzinfo is None or i.finished_at.utcoffset() is None:
                raise DivipolaManifestError("inputs.finished_at must be timezone-aware")
        if not _SHA256_RE.fullmatch(self.input_fingerprint):
            raise DivipolaManifestError("Invalid input_fingerprint")
        expected = compute_input_fingerprint(self.transform, self.raw_bucket, self.inputs)
        if self.input_fingerprint != expected:
            raise DivipolaManifestError("input_fingerprint does not match the inputs")
        if self.row_count < 1:
            raise DivipolaManifestError("row_count must be positive")
        if self.output.key != self.prefix + CSV_NAME:
            raise DivipolaManifestError("output.key is not the expected CSV key")
        if self.output.content_type != CONTENT_TYPE:
            raise DivipolaManifestError("Unexpected output.content_type")
        if not _SHA256_RE.fullmatch(self.output.sha256):
            raise DivipolaManifestError("Invalid output.sha256")
        if self.output.size_bytes <= len(HEADER) + 1:
            raise DivipolaManifestError("output.size_bytes is too small to hold any row")

    @property
    def prefix(self) -> str:
        return artifact_prefix(self.rows_updated, self.input_fingerprint)

    @property
    def manifest_key(self) -> str:
        return self.prefix + DIVIPOLA_MANIFEST_NAME

    def to_json(self) -> bytes:
        """Deterministic UTF-8 JSON: indent=2, sorted keys, LF, trailing newline."""
        text = json.dumps(
            _to_dict(self), sort_keys=True, ensure_ascii=False, indent=2, separators=(",", ": ")
        )
        return (text + "\n").encode("utf-8")

    @classmethod
    def from_json(cls, data: bytes) -> DivipolaManifest:
        """Strictly parse: exact keys and types, version and fingerprint consistency."""
        try:
            return _from_dict(json.loads(data.decode("utf-8")))
        except (UnicodeDecodeError, ValueError) as exc:
            if isinstance(exc, DivipolaManifestError):
                raise
            raise DivipolaManifestError(f"Invalid divipola manifest: {exc}") from exc


def _to_dict(m: DivipolaManifest) -> dict[str, object]:
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
        "rows_updated": m.rows_updated.isoformat(),
        "row_count": m.row_count,
        "header": m.header,
        "output": {
            "key": m.output.key,
            "sha256": m.output.sha256,
            "size_bytes": m.output.size_bytes,
            "content_type": m.output.content_type,
        },
    }


def _from_dict(raw: object) -> DivipolaManifest:
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
                "rows_updated",
                "row_count",
                "header",
                "output",
            },
            "manifest",
        )
        transform = sj.obj(top["transform"], {"name", "rules_version"}, "transform")
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
        return DivipolaManifest(
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
            rows_updated=sj.iso_date(top["rows_updated"], "rows_updated"),
            row_count=sj.integer(top["row_count"], "row_count"),
            header=sj.string(top["header"], "header"),
            output=Output(
                key=sj.string(output["key"], "output.key"),
                sha256=sj.string(output["sha256"], "output.sha256"),
                size_bytes=sj.integer(output["size_bytes"], "output.size_bytes"),
                content_type=sj.string(output["content_type"], "output.content_type"),
            ),
        )
    except sj.StrictJsonError as exc:
        raise DivipolaManifestError(str(exc)) from exc

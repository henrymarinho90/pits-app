"""Batch manifest v1 (D65): the commit marker of a raw batch and the source of the watermark (D66).

A batch is committed if and only if its manifest.json exists. Manifests are written last with
put_once, so a batch without a manifest (crashed run) is an orphan and is ignored by readers.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from pits.ingestion.raw_store import RawObjectNotFoundError, RawStore, batch_prefix

MANIFEST_VERSION = 1
MANIFEST_NAME = "manifest.json"
WATERMARK_MODES = frozenset({"incremental", "full", "since"})

_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_PARTITION_RE = re.compile(r"extraction_date=(\d{4}-\d{2}-\d{2})/")
_BATCH_RE = re.compile(r"batch_id=([0-9a-f-]{36})/")


class ManifestError(ValueError):
    """The manifest is invalid, corrupt or does not belong to the expected dataset."""


@dataclass(frozen=True)
class FileEntry:
    """One payload object of the batch (one SODA page)."""

    key: str
    offset: int
    row_count: int
    size_bytes: int
    sha256: str
    content_type: str


@dataclass(frozen=True)
class Extractor:
    name: str
    version: str


@dataclass(frozen=True)
class Query:
    order: str
    page_size: int
    where: str | None


@dataclass(frozen=True)
class Watermark:
    """D66 (no lookback): incremental reads vigenciadesde > from_exclusive.

    to_observed = high-water mark after this batch (carried forward when the batch is empty).
    """

    column: str
    mode: str
    from_exclusive: date | None
    to_observed: date | None


@dataclass(frozen=True)
class SchemaColumn:
    name: str
    data_type: str


@dataclass(frozen=True)
class Manifest:
    """Manifest v1. started_at/finished_at must be timezone-aware (serialized as UTC)."""

    source_system: str
    dataset_id: str
    source_url: str
    license: str
    attribution: str
    batch_id: str
    extraction_date: date
    started_at: datetime
    finished_at: datetime
    extractor: Extractor
    source_rows_updated_at: int | None
    app_token_used: bool
    query: Query
    watermark: Watermark
    schema: tuple[SchemaColumn, ...]
    row_count: int
    files: tuple[FileEntry, ...]
    manifest_version: int = MANIFEST_VERSION

    def __post_init__(self) -> None:
        if self.manifest_version != MANIFEST_VERSION:
            raise ManifestError(f"Unsupported manifest_version: {self.manifest_version!r}")
        if isinstance(self.extraction_date, datetime):
            raise ManifestError("extraction_date must be a date, not a datetime")
        for name in ("started_at", "finished_at"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ManifestError(f"{name} must be timezone-aware")
        if self.finished_at < self.started_at:
            raise ManifestError("finished_at must not be before started_at")
        if self.extraction_date != self.started_at.astimezone(UTC).date():
            raise ManifestError("extraction_date must equal the UTC date of started_at")
        self._check_watermark()
        self._check_schema_and_query()
        self._check_files()

    def _check_watermark(self) -> None:
        wm = self.watermark
        if wm.mode not in WATERMARK_MODES:
            raise ManifestError(f"Invalid watermark mode: {wm.mode!r}")
        if wm.mode == "full" and wm.from_exclusive is not None:
            raise ManifestError("full mode must not have watermark.from_exclusive")
        if wm.mode in ("incremental", "since") and wm.from_exclusive is None:
            raise ManifestError(f"{wm.mode} mode requires watermark.from_exclusive")
        if wm.mode == "incremental" and wm.to_observed is None:
            raise ManifestError("incremental mode requires watermark.to_observed")
        if self.row_count > 0 and wm.to_observed is None:
            raise ManifestError("a batch with rows requires watermark.to_observed")
        if (
            wm.from_exclusive is not None
            and wm.to_observed is not None
            and wm.to_observed < wm.from_exclusive
        ):
            raise ManifestError("watermark.to_observed must not be before from_exclusive")
        if wm.mode == "incremental" and self.row_count == 0 and wm.to_observed != wm.from_exclusive:
            raise ManifestError("an empty incremental batch must carry the watermark forward")

    def _check_schema_and_query(self) -> None:
        if self.query.page_size <= 0:
            raise ManifestError("query.page_size must be positive")
        names = [c.name for c in self.schema]
        if any(not n for n in names) or len(set(names)) != len(names):
            raise ManifestError("schema column names must be non-empty and unique")

    def _check_files(self) -> None:
        try:
            prefix = batch_prefix(self.source_system, self.extraction_date, self.batch_id)
        except (TypeError, ValueError) as exc:
            raise ManifestError(str(exc)) from exc
        if self.row_count != sum(f.row_count for f in self.files):
            raise ManifestError("row_count does not match the sum of files.row_count")
        keys = [f.key for f in self.files]
        if len(set(keys)) != len(keys):
            raise ManifestError("files contains duplicate keys")
        expected_offset = 0
        for entry in self.files:
            if not entry.key.startswith(prefix) or entry.key == prefix + MANIFEST_NAME:
                raise ManifestError(f"File key outside the batch prefix: {entry.key!r}")
            if not _SHA256_RE.fullmatch(entry.sha256):
                raise ManifestError(f"Invalid sha256 for {entry.key!r}")
            if min(entry.offset, entry.row_count, entry.size_bytes) < 0:
                raise ManifestError(f"Negative number in file entry {entry.key!r}")
            if entry.offset != expected_offset:
                raise ManifestError(f"Non-contiguous offset in file entry {entry.key!r}")
            expected_offset += entry.row_count

    def to_json(self) -> bytes:
        """Deterministic UTF-8 JSON, indent=2, sorted keys, trailing LF.

        indent=2 (not compact): manifests are tiny (one entry per 1000-row page) and being
        readable in the object-store console and in diffs is worth more than the saved bytes.
        Determinism comes from sort_keys, fixed separators and the fixed datetime format.
        """
        text = json.dumps(
            _to_dict(self), sort_keys=True, ensure_ascii=False, indent=2, separators=(",", ": ")
        )
        return (text + "\n").encode("utf-8")

    @classmethod
    def from_json(cls, data: bytes) -> Manifest:
        """Strictly parse a manifest: exact keys, exact types, version and consistency checks."""
        try:
            raw = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ManifestError("Manifest is not valid UTF-8 JSON") from exc
        return _from_dict(raw)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest_key(prefix: str) -> str:
    """Key of the manifest for a batch prefix ('<ss>/extraction_date=.../batch_id=.../')."""
    return prefix + MANIFEST_NAME


def _fmt_dt(value: datetime) -> str:
    return value.astimezone(UTC).strftime(_DATETIME_FORMAT)


def _fmt_date(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _to_dict(m: Manifest) -> dict[str, Any]:
    return {
        "manifest_version": m.manifest_version,
        "source_system": m.source_system,
        "dataset_id": m.dataset_id,
        "source_url": m.source_url,
        "license": m.license,
        "attribution": m.attribution,
        "batch_id": m.batch_id,
        "extraction_date": m.extraction_date.isoformat(),
        "started_at": _fmt_dt(m.started_at),
        "finished_at": _fmt_dt(m.finished_at),
        "extractor": {"name": m.extractor.name, "version": m.extractor.version},
        "source_rows_updated_at": m.source_rows_updated_at,
        "app_token_used": m.app_token_used,
        "query": {
            "order": m.query.order,
            "page_size": m.query.page_size,
            "where": m.query.where,
        },
        "watermark": {
            "column": m.watermark.column,
            "mode": m.watermark.mode,
            "from_exclusive": _fmt_date(m.watermark.from_exclusive),
            "to_observed": _fmt_date(m.watermark.to_observed),
        },
        "schema": [{"name": c.name, "data_type": c.data_type} for c in m.schema],
        "row_count": m.row_count,
        "files": [
            {
                "key": f.key,
                "offset": f.offset,
                "row_count": f.row_count,
                "size_bytes": f.size_bytes,
                "sha256": f.sha256,
                "content_type": f.content_type,
            }
            for f in m.files
        ],
    }


def _obj(value: Any, keys: set[str], where: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{where} must be an object")
    if set(value) != keys:
        missing = sorted(keys - set(value))
        extra = sorted(set(value) - keys)
        raise ManifestError(f"{where} has wrong keys (missing={missing}, unexpected={extra})")
    return value


def _str(value: Any, where: str) -> str:
    if not isinstance(value, str):
        raise ManifestError(f"{where} must be a string")
    return value


def _int(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ManifestError(f"{where} must be an integer")
    return value


def _bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise ManifestError(f"{where} must be a boolean")
    return value


def _date(value: Any, where: str) -> date:
    text = _str(value, where)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ManifestError(f"{where} must be an ISO date") from exc
    if parsed.isoformat() != text:
        raise ManifestError(f"{where} must be an ISO date (YYYY-MM-DD)")
    return parsed


def _opt_date(value: Any, where: str) -> date | None:
    return None if value is None else _date(value, where)


def _datetime(value: Any, where: str) -> datetime:
    text = _str(value, where)
    try:
        return datetime.strptime(text, _DATETIME_FORMAT).replace(tzinfo=UTC)
    except ValueError as exc:
        raise ManifestError(f"{where} must be a UTC timestamp ending in 'Z'") from exc


def _list(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise ManifestError(f"{where} must be an array")
    return value


def _from_dict(raw: Any) -> Manifest:
    top = _obj(
        raw,
        {
            "manifest_version",
            "source_system",
            "dataset_id",
            "source_url",
            "license",
            "attribution",
            "batch_id",
            "extraction_date",
            "started_at",
            "finished_at",
            "extractor",
            "source_rows_updated_at",
            "app_token_used",
            "query",
            "watermark",
            "schema",
            "row_count",
            "files",
        },
        "manifest",
    )
    version = _int(top["manifest_version"], "manifest_version")
    if version != MANIFEST_VERSION:
        raise ManifestError(f"Unsupported manifest_version: {version}")
    extractor = _obj(top["extractor"], {"name", "version"}, "extractor")
    query = _obj(top["query"], {"order", "page_size", "where"}, "query")
    wm = _obj(top["watermark"], {"column", "mode", "from_exclusive", "to_observed"}, "watermark")
    updated_at = top["source_rows_updated_at"]
    where = query["where"]
    files = []
    for i, item in enumerate(_list(top["files"], "files")):
        f = _obj(
            item,
            {"key", "offset", "row_count", "size_bytes", "sha256", "content_type"},
            f"files[{i}]",
        )
        files.append(
            FileEntry(
                key=_str(f["key"], f"files[{i}].key"),
                offset=_int(f["offset"], f"files[{i}].offset"),
                row_count=_int(f["row_count"], f"files[{i}].row_count"),
                size_bytes=_int(f["size_bytes"], f"files[{i}].size_bytes"),
                sha256=_str(f["sha256"], f"files[{i}].sha256"),
                content_type=_str(f["content_type"], f"files[{i}].content_type"),
            )
        )
    columns = []
    for i, item in enumerate(_list(top["schema"], "schema")):
        c = _obj(item, {"name", "data_type"}, f"schema[{i}]")
        columns.append(
            SchemaColumn(
                _str(c["name"], f"schema[{i}].name"), _str(c["data_type"], f"schema[{i}].data_type")
            )
        )
    return Manifest(
        manifest_version=version,
        source_system=_str(top["source_system"], "source_system"),
        dataset_id=_str(top["dataset_id"], "dataset_id"),
        source_url=_str(top["source_url"], "source_url"),
        license=_str(top["license"], "license"),
        attribution=_str(top["attribution"], "attribution"),
        batch_id=_str(top["batch_id"], "batch_id"),
        extraction_date=_date(top["extraction_date"], "extraction_date"),
        started_at=_datetime(top["started_at"], "started_at"),
        finished_at=_datetime(top["finished_at"], "finished_at"),
        extractor=Extractor(
            _str(extractor["name"], "extractor.name"),
            _str(extractor["version"], "extractor.version"),
        ),
        source_rows_updated_at=None
        if updated_at is None
        else _int(updated_at, "source_rows_updated_at"),
        app_token_used=_bool(top["app_token_used"], "app_token_used"),
        query=Query(
            order=_str(query["order"], "query.order"),
            page_size=_int(query["page_size"], "query.page_size"),
            where=None if where is None else _str(where, "query.where"),
        ),
        watermark=Watermark(
            column=_str(wm["column"], "watermark.column"),
            mode=_str(wm["mode"], "watermark.mode"),
            from_exclusive=_opt_date(wm["from_exclusive"], "watermark.from_exclusive"),
            to_observed=_opt_date(wm["to_observed"], "watermark.to_observed"),
        ),
        schema=tuple(columns),
        row_count=_int(top["row_count"], "row_count"),
        files=tuple(files),
    )


def commit_order_key(m: Manifest) -> tuple[date, datetime, str]:
    """Total commit order of batches: (extraction_date, finished_at, batch_id).

    Independent of LIST order; batch_id is only a deterministic tie-break (never read as a date).
    """
    return (m.extraction_date, m.finished_at, m.batch_id)


def _partitions(store: RawStore, source_system: str) -> list[tuple[date, str]]:
    """Partition prefixes of a source system, sorted ascending by date (strict on odd prefixes)."""
    root = f"{source_system}/"
    partitions: list[tuple[date, str]] = []
    for prefix in store.list_prefixes(root):
        match = _PARTITION_RE.fullmatch(prefix[len(root) :]) if prefix.startswith(root) else None
        if match is None:
            raise ManifestError(f"Unexpected prefix under '{root}': {prefix!r}")
        partitions.append((_date(match.group(1), f"partition {prefix!r}"), prefix))
    return sorted(partitions)


def _read_partition(
    store: RawStore, source_system: str, dataset_id: str, partition_date: date, partition: str
) -> list[Manifest]:
    """Strictly read the committed manifests of one partition (orphans are skipped)."""
    committed: list[Manifest] = []
    for batch in store.list_prefixes(partition):
        match = (
            _BATCH_RE.fullmatch(batch[len(partition) :]) if batch.startswith(partition) else None
        )
        if match is None:
            raise ManifestError(f"Unexpected prefix under '{partition}': {batch!r}")
        batch_id = match.group(1)
        try:
            valid = str(uuid.UUID(batch_id)) == batch_id
        except ValueError:
            valid = False
        if not valid:
            raise ManifestError(f"Invalid batch_id in prefix {batch!r}")
        key = manifest_key(batch)
        try:
            data = store.get(key)
        except RawObjectNotFoundError:
            continue  # orphan batch: no manifest, never committed
        try:
            manifest = Manifest.from_json(data)
        except ManifestError as exc:
            raise ManifestError(f"{key}: {exc}") from exc
        if (manifest.source_system, manifest.dataset_id) != (source_system, dataset_id):
            raise ManifestError(
                f"{key}: belongs to {manifest.source_system}/{manifest.dataset_id}, "
                f"expected {source_system}/{dataset_id}"
            )
        if manifest.batch_id != batch_id or manifest.extraction_date != partition_date:
            raise ManifestError(f"{key}: batch_id/extraction_date do not match its location")
        committed.append(manifest)
    return committed


def list_committed(store: RawStore, source_system: str, dataset_id: str) -> tuple[Manifest, ...]:
    """Return every committed manifest of (source_system, dataset_id) in commit order.

    Reads all partitions with the same strict validation as find_latest_committed: a corrupt
    manifest in any partition, an unexpected prefix, or a manifest of another source/dataset or
    in the wrong location raises ManifestError. Orphan batches (no manifest) are ignored.
    """
    result: list[Manifest] = []
    for partition_date, partition in _partitions(store, source_system):
        result.extend(_read_partition(store, source_system, dataset_id, partition_date, partition))
    return tuple(sorted(result, key=commit_order_key))


def find_latest_committed(store: RawStore, source_system: str, dataset_id: str) -> Manifest | None:
    """Return the most recent committed manifest of (source_system, dataset_id), or None.

    Partitions are scanned newest first and only until one holds a committed batch; inside it
    the greatest commit_order_key wins (equals list_committed(...)[-1]). Batches without
    manifest.json are orphans (crashed runs) and are skipped. Unexpected prefixes, corrupt
    manifests, or manifests of another source/dataset/batch fail loudly: silently skipping
    them could make the next incremental run reload or skip data.
    """
    for partition_date, partition in reversed(_partitions(store, source_system)):
        committed = _read_partition(store, source_system, dataset_id, partition_date, partition)
        if committed:
            return max(committed, key=commit_order_key)
    return None

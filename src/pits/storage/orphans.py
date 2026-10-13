"""Read-only inventory of orphan prefixes in the raw and normalized buckets (D107).

A raw batch (`<source_system>/extraction_date=.../batch_id=<uuid>/`) or a normalized artifact
(`.../fingerprint=<sha256>/`) is committed only when its `manifest.json` exists (the manifest is
written last). Objects without it are leftovers of an interrupted write.

The listing has no delimiter. Correctness depends on every group prefix ending in '/': the
keys of one group are then contiguous both in lexicographic order and in SeaweedFS directory
order, so groups are closed in streaming and memory stays constant. No global key order is
assumed. Only `list_objects_v2` is ever called; nothing is written or deleted.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

from botocore.client import BaseClient
from botocore.exceptions import ClientError

MANIFEST_NAME = "manifest.json"
MAX_UNEXPECTED_SAMPLES = 20

_SOURCE = r"[a-z][a-z0-9_]*"
_DATE = r"\d{4}-\d{2}-\d{2}"
# group 1 = the group prefix (ends with '/'), group 2 = the rest of the key.
RAW_LAYOUT = re.compile(
    rf"({_SOURCE}/extraction_date={_DATE}/batch_id=[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-"
    rf"[0-9a-f]{{4}}-[0-9a-f]{{12}}/)(.+)",
    re.DOTALL,
)
NORMALIZED_LAYOUT = re.compile(
    rf"((?:fx_rate/source_system={_SOURCE}/inputs_until={_DATE}"
    rf"|vehicle_fleet_snapshot/source_system={_SOURCE}/publication_month=\d{{4}}-\d{{2}}"
    rf"|divipola_municipality/source_system={_SOURCE}/rows_updated={_DATE})"
    rf"/fingerprint=[0-9a-f]{{64}}/)(.+)",
    re.DOTALL,
)

_TRANSIENT_CODES = {"SlowDown", "RequestTimeout", "InternalError", "ServiceUnavailable"}
_DENIED_CODES = {"403", "Forbidden", "AccessDenied"}


class OrphansError(RuntimeError):
    """The inventory cannot run (permissions, missing bucket): permanent."""


class OrphansTransientError(OrphansError):
    """The storage answered with a transient failure (5xx, throttling): retry later."""


@dataclass(frozen=True)
class Orphan:
    bucket: str
    prefix: str
    objects: int
    bytes: int
    newest: datetime


@dataclass
class BucketReport:
    bucket: str
    groups: int = 0
    committed: int = 0
    orphans: int = 0
    orphan_bytes: int = 0
    unexpected: int = 0
    unexpected_samples: list[str] = field(default_factory=list)


@dataclass
class _Group:
    prefix: str
    objects: int = 0
    size: int = 0
    newest: datetime | None = None
    has_manifest: bool = False


def _classify(exc: ClientError, bucket: str) -> OrphansError:
    code = str(exc.response.get("Error", {}).get("Code", ""))
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    if code in _DENIED_CODES:
        return OrphansError(f"Access denied listing bucket '{bucket}'")
    if code in _TRANSIENT_CODES or (isinstance(status, int) and status >= 500):
        return OrphansTransientError(f"list_objects_v2 failed for '{bucket}': {code or status}")
    return OrphansError(f"list_objects_v2 failed for '{bucket}': {code or 'unknown error'}")


def _iter_objects(client: BaseClient, bucket: str) -> Iterator[tuple[str, int, datetime]]:
    """Yield (key, size, last_modified) page by page, in key order."""
    token: str | None = None
    while True:
        kwargs: dict[str, str] = {"Bucket": bucket}
        if token:
            kwargs["ContinuationToken"] = token
        try:
            page = client.list_objects_v2(**kwargs)
        except ClientError as exc:
            raise _classify(exc, bucket) from exc
        for obj in page.get("Contents", []):
            yield obj["Key"], int(obj["Size"]), obj["LastModified"]
        if not page.get("IsTruncated"):
            return
        token = page.get("NextContinuationToken")
        if not token:
            raise OrphansError(f"Truncated listing of '{bucket}' without NextContinuationToken")


def scan_bucket(
    client: BaseClient,
    bucket: str,
    layout: re.Pattern[str],
    on_orphan: Callable[[Orphan], None],
) -> BucketReport:
    """Stream the bucket listing; call `on_orphan` as each manifest-less group is closed."""
    report = BucketReport(bucket)
    current: _Group | None = None

    def close(group: _Group) -> None:
        report.groups += 1
        if group.has_manifest:
            report.committed += 1
            return
        if group.newest is None:  # unreachable: a group has at least one object
            raise OrphansError("internal error: empty group")
        report.orphans += 1
        report.orphan_bytes += group.size
        on_orphan(Orphan(bucket, group.prefix, group.objects, group.size, group.newest))

    for key, size, modified in _iter_objects(client, bucket):
        match = layout.fullmatch(key)
        if match is None:
            report.unexpected += 1
            if len(report.unexpected_samples) < MAX_UNEXPECTED_SAMPLES:
                report.unexpected_samples.append(key)
            continue
        prefix, rest = match.group(1), match.group(2)
        if current is None or current.prefix != prefix:
            if current is not None:
                close(current)
            current = _Group(prefix)
        current.objects += 1
        current.size += size
        if current.newest is None or modified > current.newest:
            current.newest = modified
        if rest == MANIFEST_NAME:
            current.has_manifest = True
    if current is not None:
        close(current)
    return report


def format_timestamp(value: datetime) -> str:
    """ISO-8601 in UTC (naive datetimes are taken as UTC)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def escape_key(key: str) -> str:
    """Keys may hold control characters; keep each output record on one line."""
    return key.encode("unicode_escape").decode("ascii")

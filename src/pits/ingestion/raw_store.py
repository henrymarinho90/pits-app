"""Write-once raw object store abstraction (D65) with S3 and in-memory implementations."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Protocol

from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

MAX_OBJECT_BYTES = 8 * 1024 * 1024  # single put_object, no multipart (D65)

_PRECONDITION_CODES = {"412", "PreconditionFailed"}
_NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound"}
_SOURCE_SYSTEM_RE = re.compile(r"[a-z][a-z0-9_]*")


class RawStoreError(RuntimeError):
    """Raised on any raw store failure; messages never contain credentials."""


class RawStoreTransientError(RawStoreError):
    """Network/transport failure talking to the store (timeouts, connection errors)."""


class RawObjectExistsError(RawStoreError):
    """The key already exists; raw objects are write-once and never retried."""


class RawObjectNotFoundError(RawStoreError):
    """The key does not exist."""


class RawStore(Protocol):
    """Minimal raw store contract used by extractors."""

    def put_once(self, key: str, body: bytes, content_type: str) -> None: ...

    def list_prefixes(self, prefix: str) -> list[str]: ...

    def get(self, key: str) -> bytes: ...


def batch_prefix(source_system: str, extraction_date: date, batch_id: str) -> str:
    """Return '<source_system>/extraction_date=YYYY-MM-DD/batch_id=<uuid>/'."""
    if not _SOURCE_SYSTEM_RE.fullmatch(source_system):
        raise ValueError("source_system must be ASCII snake_case ([a-z][a-z0-9_]*)")
    if isinstance(extraction_date, datetime):
        raise TypeError("extraction_date must be a date, not a datetime")
    try:
        canonical = str(uuid.UUID(batch_id))
    except ValueError as exc:
        raise ValueError("batch_id must be a valid UUID") from exc
    if canonical != batch_id:
        raise ValueError("batch_id must be a lowercase hyphenated UUID")
    return f"{source_system}/extraction_date={extraction_date.isoformat()}/batch_id={batch_id}/"


def _check_size(key: str, body: bytes) -> None:
    if len(body) > MAX_OBJECT_BYTES:
        raise RawStoreError(
            f"Object '{key}' is {len(body)} bytes, above the {MAX_OBJECT_BYTES} byte limit"
        )


def _check_key(key: str) -> None:
    if not key:
        raise ValueError("key must not be empty")


def _transient(operation: str, target: str, exc: BotoCoreError) -> RawStoreTransientError:
    # Only the class name: transport errors may embed endpoints.
    return RawStoreTransientError(f"{operation} failed for '{target}': {type(exc).__name__}")


def _code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


class S3RawStore:
    """RawStore backed by an S3-compatible bucket; writes use If-None-Match: *."""

    def __init__(self, client: BaseClient, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def put_once(self, key: str, body: bytes, content_type: str) -> None:
        _check_key(key)
        _check_size(key, body)
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
                IfNoneMatch="*",
            )
        except ClientError as exc:
            code = _code(exc)
            if code in _PRECONDITION_CODES:
                raise RawObjectExistsError(f"Object '{key}' already exists") from exc
            raise RawStoreError(f"put_object failed for '{key}': {code or 'unknown'}") from exc
        except BotoCoreError as exc:
            raise _transient("put_object", key, exc) from None

    def list_prefixes(self, prefix: str) -> list[str]:
        prefixes: list[str] = []
        kwargs: dict[str, object] = {"Bucket": self._bucket, "Prefix": prefix, "Delimiter": "/"}
        while True:
            try:
                resp = self._client.list_objects_v2(**kwargs)
            except ClientError as exc:
                raise RawStoreError(
                    f"list_objects_v2 failed for prefix '{prefix}': {_code(exc) or 'unknown'}"
                ) from exc
            except BotoCoreError as exc:
                raise _transient("list_objects_v2", prefix, exc) from None
            prefixes.extend(p["Prefix"] for p in resp.get("CommonPrefixes", []))
            if not resp.get("IsTruncated"):
                return prefixes
            kwargs["ContinuationToken"] = resp["NextContinuationToken"]

    def get(self, key: str) -> bytes:
        _check_key(key)
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
            return resp["Body"].read()
        except ClientError as exc:
            code = _code(exc)
            if code in _NOT_FOUND_CODES:
                raise RawObjectNotFoundError(f"Object '{key}' not found") from exc
            raise RawStoreError(f"get_object failed for '{key}': {code or 'unknown'}") from exc
        except BotoCoreError as exc:
            raise _transient("get_object", key, exc) from None


class MemoryRawStore:
    """In-memory RawStore with the same semantics as S3RawStore (for tests)."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.content_types: dict[str, str] = {}

    def put_once(self, key: str, body: bytes, content_type: str) -> None:
        _check_key(key)
        _check_size(key, body)
        if key in self.objects:
            raise RawObjectExistsError(f"Object '{key}' already exists")
        self.objects[key] = bytes(body)
        self.content_types[key] = content_type

    def list_prefixes(self, prefix: str) -> list[str]:
        found = {
            prefix + key[len(prefix) :].split("/", 1)[0] + "/"
            for key in self.objects
            if key.startswith(prefix) and "/" in key[len(prefix) :]
        }
        return sorted(found)

    def get(self, key: str) -> bytes:
        _check_key(key)
        try:
            return self.objects[key]
        except KeyError:
            raise RawObjectNotFoundError(f"Object '{key}' not found") from None

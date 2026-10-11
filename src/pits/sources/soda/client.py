"""Minimal SODA HTTP client with explicit timeouts and bounded retries (D64)."""

from __future__ import annotations

import json
import math
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from pits.sources.soda.settings import SodaSettings

MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 1.0  # 1, 2, 4 s between attempts (+ jitter)
MAX_RETRY_AFTER_SECONDS = 60.0
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
TIMEOUT = httpx.Timeout(connect=10, read=30, write=10, pool=10)


class SodaError(Exception):
    """Base class for SODA client errors; messages never contain the app token."""


class SodaTransientError(SodaError):
    """Retries were exhausted on a transient failure (429, 5xx, transport)."""


class SodaPermanentError(SodaError):
    """The request cannot succeed by retrying (4xx, malformed response)."""


@dataclass(frozen=True)
class RawPage:
    """One response: exact bytes (for the raw layer) and the parsed rows."""

    body: bytes
    rows: list[dict[str, Any]]


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After", "").strip()
    try:
        seconds = float(value)
    except ValueError:
        return None  # HTTP-date form is not supported; fall back to backoff
    if not math.isfinite(seconds):
        return None
    return min(max(seconds, 0.0), MAX_RETRY_AFTER_SECONDS)


def _parse_json(path: str, body: bytes) -> Any:
    try:
        return json.loads(body)
    except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError
        raise SodaPermanentError(f"GET {path}: response is not valid JSON") from exc


class SodaClient:
    """Reads dataset metadata and resource pages from a Socrata portal."""

    def __init__(
        self,
        settings: SodaSettings,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        headers = {"Accept": "application/json"}
        if settings.app_token:
            headers["X-App-Token"] = settings.app_token
        self._http = httpx.Client(
            base_url=settings.base_url,
            headers=headers,
            timeout=TIMEOUT,
            transport=transport,
        )
        self._sleep = sleep
        self._jitter = jitter

    def __repr__(self) -> str:
        return f"SodaClient(base_url={str(self._http.base_url)!r})"

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> SodaClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get_metadata(self, dataset_id: str) -> dict[str, Any]:
        """Return the dataset view metadata (/api/views/<id>.json)."""
        path = f"/api/views/{dataset_id}.json"
        data = _parse_json(path, self._get(path, None).content)
        if not isinstance(data, dict):
            raise SodaPermanentError(f"GET {path}: expected a JSON object")
        return data

    def get_page(self, dataset_id: str, params: Mapping[str, str | int]) -> RawPage:
        """Return one page of rows (/resource/<id>.json) with the exact response bytes."""
        path = f"/resource/{dataset_id}.json"
        body = self._get(path, params).content
        rows = _parse_json(path, body)
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise SodaPermanentError(f"GET {path}: expected a JSON array of objects")
        return RawPage(body=body, rows=rows)

    def _get(self, path: str, params: Mapping[str, str | int] | None) -> httpx.Response:
        last = "unknown error"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            delay: float | None = None
            try:
                response = self._http.get(path, params=params)
            except httpx.TransportError as exc:
                last = f"transport error ({type(exc).__name__})"
            except httpx.RequestError as exc:
                raise SodaPermanentError(
                    f"GET {path}: request failed ({type(exc).__name__})"
                ) from None
            else:
                status = response.status_code
                if 200 <= status < 300:  # redirects are not followed (would leak the token)
                    return response
                if status not in RETRYABLE_STATUS:
                    raise SodaPermanentError(f"GET {path}: HTTP {status}")
                last = f"HTTP {status}"
                delay = _retry_after(response)
            if attempt == MAX_ATTEMPTS:
                break
            if delay is None:
                delay = BACKOFF_BASE_SECONDS * 2 ** (attempt - 1) + self._jitter()
            self._sleep(delay)
        raise SodaTransientError(f"GET {path}: {last} after {MAX_ATTEMPTS} attempts")

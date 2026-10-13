"""Shared DIVIPOLA builders for tests (not a test module; no test_ prefix).

`raw_row` / `rows` build valid raw rows; `FakeDivipola` is a Socrata stand-in served through
httpx.MockTransport; `put_divipola_batch` writes a committed raw batch like the extractor would.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

import httpx

from pits.ingestion.manifest import (
    Extractor,
    FileEntry,
    Manifest,
    Query,
    Watermark,
    manifest_key,
    sha256_hex,
)
from pits.ingestion.raw_store import RawStore, batch_prefix
from pits.sources.divipola.contract import (
    ATTRIBUTION,
    DATASET_ID,
    EXPECTED_SCHEMA,
    LICENSE,
    SOURCE_SYSTEM,
    SOURCE_URL,
    WATERMARK_COLUMN,
)
from pits.sources.soda.client import SodaClient
from pits.sources.soda.settings import SodaSettings

B1 = "0b6f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a10"
B2 = "1c7a7d2f-4d2b-4a1f-8b62-3e5d7a9fab21"
COLUMNS = [{"fieldName": c.name, "dataTypeName": c.data_type} for c in EXPECTED_SCHEMA]
# 2025-01-24T10:04:32Z, the real rowsUpdatedAt of the dataset (verified 2026-10-13).
ROWS_UPDATED_AT = 1737751472
ROWS_UPDATED_DATE = date(2025, 1, 24)


def raw_row(i: int = 0, **over: str) -> dict[str, str]:
    """One valid raw row; every i gives a distinct cod_mpio and nom_mpio (department 05)."""
    base = {
        "cod_dpto": "05",
        "dpto": "ANTIOQUIA",
        "cod_mpio": f"05{i + 1:03d}",
        "nom_mpio": f"MUNICIPIO {i}",
        "tipo_municipio": "Municipio",
        "longitud": "-75,581775",
        "latitud": "6,246631",
    }
    return {**base, **over}


def rows(n: int) -> list[dict[str, str]]:
    return [raw_row(i) for i in range(n)]


class FakeDivipola:
    """Socrata stand-in for gdxc-w37w served through httpx.MockTransport."""

    def __init__(self, data: list[dict], updated_at: int = ROWS_UPDATED_AT) -> None:
        self.rows = data
        self.columns = COLUMNS
        self.updated_at = updated_at
        self.total_override: int | None = None
        self.bump_after_page_calls: int | None = None
        self.status: int | None = None
        self.requests: list[httpx.Request] = []
        self._page_calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.startswith("/api/views/"):
            return httpx.Response(
                200, json={"rowsUpdatedAt": self.updated_at, "columns": self.columns}
            )
        if self.status:
            return httpx.Response(self.status)
        params = request.url.params
        if params.get("$select") == "count(*)":
            count = self.total_override if self.total_override is not None else len(self.rows)
            return httpx.Response(200, json=[{"count": str(count)}])
        self._page_calls += 1
        offset, limit = int(params["$offset"]), int(params["$limit"])
        body = json.dumps(self.rows[offset : offset + limit], ensure_ascii=False).encode("utf-8")
        if self.bump_after_page_calls == self._page_calls:
            self.updated_at += 1
        return httpx.Response(200, content=body)

    def client(self, app_token: str | None = None) -> SodaClient:
        return SodaClient(
            SodaSettings(base_url="https://example.test", app_token=app_token),
            transport=httpx.MockTransport(self.handler),
            sleep=lambda s: None,
            jitter=lambda: 0.0,
        )

    def page_params(self) -> list[httpx.QueryParams]:
        return [
            r.url.params
            for r in self.requests
            if r.url.path.startswith("/resource/") and "$select" not in r.url.params
        ]


class Clock:
    def __init__(self, first: datetime = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)) -> None:
        self.t = first

    def __call__(self) -> datetime:
        self.t += timedelta(seconds=10)
        return self.t


def put_divipola_batch(
    store: RawStore,
    batch_id: str,
    day: date,
    data: Sequence[dict[str, str]],
    *,
    updated_at: int = ROWS_UPDATED_AT,
    page_size: int = 3,
) -> Manifest:
    """Write payload pages + manifest like the extractor would (a committed full snapshot)."""
    prefix = batch_prefix(SOURCE_SYSTEM, day, batch_id)
    files: list[FileEntry] = []
    offset = 0
    for start in range(0, len(data), page_size):
        page = list(data[start : start + page_size])
        body = json.dumps(page, ensure_ascii=False).encode("utf-8")
        key = f"{prefix}payload-{len(files):05d}.json"
        store.put_once(key, body, "application/json")
        files.append(
            FileEntry(key, offset, len(page), len(body), sha256_hex(body), "application/json")
        )
        offset += len(page)
    started = datetime(day.year, day.month, day.day, 12, tzinfo=UTC)
    manifest = Manifest(
        source_system=SOURCE_SYSTEM,
        dataset_id=DATASET_ID,
        source_url=SOURCE_URL,
        license=LICENSE,
        attribution=ATTRIBUTION,
        batch_id=batch_id,
        extraction_date=day,
        started_at=started,
        finished_at=started,
        extractor=Extractor("pits.sources.divipola", "test"),
        source_rows_updated_at=updated_at,
        app_token_used=False,
        query=Query(":id ASC", page_size, None),
        watermark=Watermark(
            WATERMARK_COLUMN, "full", None, datetime.fromtimestamp(updated_at, UTC).date()
        ),
        schema=EXPECTED_SCHEMA,
        row_count=offset,
        files=tuple(files),
    )
    store.put_once(manifest_key(prefix), manifest.to_json(), "application/json")
    return manifest

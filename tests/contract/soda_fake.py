"""Shared fake SODA data for normalize tests (offline CLI tests and S3 contract tests).

Not a test module (no test_ prefix). `tests/contract` is on pythonpath (pyproject).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta

import httpx

from pits.ingestion.raw_store import RawStore
from pits.sources.soda.client import SodaClient
from pits.sources.soda.settings import SodaSettings
from pits.sources.trm.contract import BACKFILL_FROM
from pits.sources.trm.extract import Mode, extract_trm

COLUMNS = [
    {"fieldName": "valor", "dataTypeName": "number"},
    {"fieldName": "unidad", "dataTypeName": "text"},
    {"fieldName": "vigenciadesde", "dataTypeName": "calendar_date"},
    {"fieldName": "vigenciahasta", "dataTypeName": "calendar_date"},
]


def _row(frm: date, to: date, valor: str) -> dict[str, str]:
    return {
        "valor": valor,
        "unidad": "COP",
        "vigenciadesde": f"{frm.isoformat()}T00:00:00.000",
        "vigenciahasta": f"{to.isoformat()}T00:00:00.000",
    }


def contiguous_rows() -> list[dict[str, str]]:
    """Gap-free rows from BACKFILL_FROM: ten 3-day ranges, then one 4-day range (max = 4)."""
    rows = []
    start = BACKFILL_FROM
    for i in range(10):
        rows.append(_row(start, start + timedelta(days=2), f"{3000 + i}.5"))
        start += timedelta(days=3)
    rows.append(_row(start, start + timedelta(days=3), "3100.25"))
    return rows


def soda_client(rows: list[dict[str, str]]) -> SodaClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/views/"):
            return httpx.Response(200, json={"rowsUpdatedAt": 100, "columns": COLUMNS})
        params = request.url.params
        selected = rows
        match = re.fullmatch(
            r"vigenciadesde > '(\d{4}-\d{2}-\d{2})T00:00:00\.000'", params.get("$where", "")
        )
        if match:
            selected = [r for r in rows if r["vigenciadesde"][:10] > match.group(1)]
        if params.get("$select") == "count(*)":
            return httpx.Response(200, json=[{"count": str(len(selected))}])
        offset, limit = int(params["$offset"]), int(params["$limit"])
        return httpx.Response(200, content=json.dumps(selected[offset : offset + limit]).encode())

    return SodaClient(
        SodaSettings(base_url="https://example.test", app_token=None),
        transport=httpx.MockTransport(handler),
        sleep=lambda s: None,
        jitter=lambda: 0.0,
    )


def extract_batch(
    store: RawStore,
    rows: list[dict[str, str]],
    *,
    batch_id: str,
    day: date,
    mode: Mode = "full",
    page_size: int = 4,
) -> None:
    """Run the real extractor against the fake SODA into `store` (several payload pages)."""
    t = datetime(day.year, day.month, day.day, 12, tzinfo=UTC)
    extract_trm(
        soda_client(rows),
        store,
        mode=mode,
        since=None,
        now=lambda: t,
        new_batch_id=lambda: batch_id,
        extractor_version="test",
        page_size=page_size,
    )

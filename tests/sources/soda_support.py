"""Shared fake SODA for the TRM and RUNT extractor tests (not a test module; no test_ prefix)."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta

import httpx

from pits.sources.soda.client import SodaClient
from pits.sources.soda.settings import SodaSettings

START = date(2026, 1, 1)
COLUMNS = [
    {"fieldName": "valor", "dataTypeName": "number"},
    {"fieldName": "unidad", "dataTypeName": "text"},
    {"fieldName": "vigenciadesde", "dataTypeName": "calendar_date"},
    {"fieldName": "vigenciahasta", "dataTypeName": "calendar_date"},
]


def row(day: date) -> dict:
    stamp = f"{day.isoformat()}T00:00:00.000"
    return {"valor": "3900.5", "unidad": "COP", "vigenciadesde": stamp, "vigenciahasta": stamp}


def make_rows(n: int, start: date = START) -> list[dict]:
    return [row(start + timedelta(days=i)) for i in range(n)]


class FakeSoda:
    """Socrata stand-in served through httpx.MockTransport."""

    def __init__(self, rows, columns=None, updated_at=100):
        self.rows = rows
        self.columns = COLUMNS if columns is None else columns
        self.updated_at = updated_at
        self.requests: list[httpx.Request] = []
        self.bump_after_resource_calls: int | None = None
        self.resource_status: int | None = None
        self.meta_override: dict | None = None
        self.token: str | None = None
        self._resource_calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.startswith("/api/views/"):
            meta = {"rowsUpdatedAt": self.updated_at, "columns": self.columns}
            if self.meta_override is not None:
                meta = self.meta_override
            return httpx.Response(200, json=meta)
        self._resource_calls += 1
        if self.resource_status:
            return httpx.Response(self.resource_status)
        params = request.url.params
        rows = self.rows
        match = re.fullmatch(
            r"vigenciadesde (>=?) '(\d{4}-\d{2}-\d{2})T00:00:00\.000'", params.get("$where", "")
        )
        if match:
            op, day = match.groups()
            rows = [
                r
                for r in rows
                if (r["vigenciadesde"][:10] >= day if op == ">=" else r["vigenciadesde"][:10] > day)
            ]
        offset, limit = int(params["$offset"]), int(params["$limit"])
        body = json.dumps(rows[offset : offset + limit]).encode()
        if self.bump_after_resource_calls == self._resource_calls:
            self.updated_at += 1
        return httpx.Response(200, content=body)

    def client(self) -> SodaClient:
        return SodaClient(
            SodaSettings(base_url="https://example.test", app_token=self.token),
            transport=httpx.MockTransport(self.handler),
            sleep=lambda s: None,
            jitter=lambda: 0.0,
        )

    def resource_params(self) -> list[httpx.QueryParams]:
        return [r.url.params for r in self.requests if r.url.path.startswith("/resource/")]

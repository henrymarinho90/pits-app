"""Shared builders for the regional brand fleet tests (not a test module; no test_ prefix).

`boyaca_row` / `risaralda_row` build valid synthetic raw rows; `FakeBrandFleet` is a Socrata
stand-in served through httpx.MockTransport that honours $select like the real API;
`put_brand_batch` writes a committed raw batch like the extractor would. All data is synthetic.
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
from pits.sources.brand_fleet.contract import (
    LICENSE,
    ORDER,
    WATERMARK_COLUMN,
    BrandFleetSource,
    get_source,
)
from pits.sources.soda.client import SodaClient
from pits.sources.soda.settings import SodaSettings

B1 = "0b6f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a10"
B2 = "1c7a7d2f-4d2b-4a1f-8b62-3e5d7a9fab21"
BOYACA = get_source("boyaca")
RISARALDA = get_source("risaralda")
ROWS_UPDATED_AT = 1783366796  # 2026-07-06
ROWS_UPDATED_DATE = date(2026, 7, 6)


def columns(source: BrandFleetSource) -> list[dict[str, str]]:
    return [{"fieldName": c.name, "dataTypeName": c.data_type} for c in source.source_schema]


def boyaca_row(i: int = 0, **over: str) -> dict[str, str]:
    """A valid Boyaca row; optional keys (modelo, cilindraje) are present."""
    base = {
        "n": str(i + 1),
        "motivo_ingreso": "MATRICULA INICIAL",
        "cod_dane": "15001",
        "dane_mun": "15001",
        "provincia": "CENTRO",
        "municipio": "TUNJA",
        "clase": "AUTOMOVIL",
        "marca": "MARCA X",
        "linea": f"LINEA {i % 3}",
        "modelo": "2015",
        "carroceria": "SEDAN",
        "pasajeros": "5",
        "tonelaje": "0",
        "cilindraje": "1600",
        "servicio": "PARTICULAR",
        "estado": "ACTIVO",
        "blindaje": "NO",
        "importado": "NO",
    }
    return {**base, **over}


def risaralda_row(i: int = 0, **over: str) -> dict[str, str]:
    """A valid Risaralda row as served with the contract $select (no plate)."""
    base = {
        "clase": "MOTOCICLETA",
        "marca": "MARCA Y",
        "modelo": "2020",
        "linea": f"LINEA {i % 3}",
        "cilindraje": "125",
    }
    return {**base, **over}


class FakeBrandFleet:
    """Socrata stand-in for one regional dataset served through httpx.MockTransport."""

    def __init__(
        self,
        source: BrandFleetSource,
        data: list[dict],
        updated_at: int = ROWS_UPDATED_AT,
        *,
        honour_select: bool = True,
    ) -> None:
        self.source = source
        self.rows = data
        self.columns = columns(source)
        self.updated_at = updated_at
        self.honour_select = honour_select
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
        page = self.rows[offset : offset + limit]
        if self.honour_select:
            selected = params["$select"].split(",")
            page = [{k: v for k, v in r.items() if k in selected} for r in page]
        body = json.dumps(page, ensure_ascii=False).encode("utf-8")
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

    def count_requests(self) -> list[httpx.QueryParams]:
        return [
            r.url.params
            for r in self.requests
            if r.url.path.startswith("/resource/") and r.url.params.get("$select") == "count(*)"
        ]

    def page_params(self) -> list[httpx.QueryParams]:
        return [
            r.url.params
            for r in self.requests
            if r.url.path.startswith("/resource/") and r.url.params.get("$select") != "count(*)"
        ]


class Clock:
    def __init__(self, first: datetime = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)) -> None:
        self.t = first

    def __call__(self) -> datetime:
        self.t += timedelta(seconds=10)
        return self.t


def put_brand_batch(
    store: RawStore,
    source: BrandFleetSource,
    batch_id: str,
    day: date,
    data: Sequence[dict[str, str]],
    *,
    updated_at: int = ROWS_UPDATED_AT,
    page_size: int = 3,
) -> Manifest:
    """Write payload pages + manifest like the extractor would (a committed full snapshot)."""
    prefix = batch_prefix(source.source_system, day, batch_id)
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
        source_system=source.source_system,
        dataset_id=source.dataset_id,
        source_url=source.source_url,
        license=LICENSE,
        attribution=source.attribution,
        batch_id=batch_id,
        extraction_date=day,
        started_at=started,
        finished_at=started,
        extractor=Extractor("pits.sources.brand_fleet", "test"),
        source_rows_updated_at=updated_at,
        app_token_used=False,
        query=Query(ORDER, page_size, None),
        watermark=Watermark(
            WATERMARK_COLUMN, "full", None, datetime.fromtimestamp(updated_at, UTC).date()
        ),
        schema=source.requested_schema,
        row_count=offset,
        files=tuple(files),
    )
    store.put_once(manifest_key(prefix), manifest.to_json(), "application/json")
    return manifest

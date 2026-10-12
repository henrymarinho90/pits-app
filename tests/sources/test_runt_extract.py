"""Offline tests for the RUNT extractor (httpx.MockTransport + MemoryRawStore)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from soda_support import FakeSoda, make_rows

from pits.ingestion.manifest import Manifest, find_latest_committed, manifest_key, sha256_hex
from pits.ingestion.raw_store import MemoryRawStore, batch_prefix
from pits.sources.extract_common import ExtractPermanentError, ExtractTransientError
from pits.sources.runt.contract import DATASET_ID, ORDER, SOURCE_SYSTEM
from pits.sources.runt.extract import extract_runt
from pits.sources.soda.client import SodaClient
from pits.sources.soda.settings import SodaSettings
from pits.sources.trm.extract import extract_trm

B1 = "0b6f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a10"
B2 = "1c7a7d2f-4d2b-4a1f-8b62-3e5d7a9fab21"
COLUMNS = [
    {"fieldName": "nombre_departamento", "dataTypeName": "text"},
    {"fieldName": "nombre_municipio", "dataTypeName": "text"},
    {"fieldName": "nombre_servicio", "dataTypeName": "text"},
    {"fieldName": "estado_del_vehiculo", "dataTypeName": "text"},
    {"fieldName": "nombre_de_la_clase", "dataTypeName": "text"},
    {"fieldName": "fecha_de_registro", "dataTypeName": "number"},
    {"fieldName": "cantidad", "dataTypeName": "number"},
    {"fieldName": "mes_de_publicacion", "dataTypeName": "text"},
    {"fieldName": "a_o_de_publicacion", "dataTypeName": "number"},
]


def row(i: int = 0, **over: str) -> dict:
    base = {
        "nombre_departamento": "ANTIOQUIA",
        "nombre_municipio": f"MUNI{i}",
        "nombre_servicio": "PARTICULAR",
        "estado_del_vehiculo": "ACTIVO",
        "nombre_de_la_clase": "CAMPERO",
        "fecha_de_registro": "1999",
        "cantidad": "3",
        "mes_de_publicacion": "OCTUBRE",
        "a_o_de_publicacion": "2026",
    }
    return {**base, **over}


class FakeRunt:
    """Socrata stand-in for u3vn-bdcy served through httpx.MockTransport."""

    def __init__(self, rows, updated_at=100):
        self.rows = rows
        self.columns = COLUMNS
        self.updated_at = updated_at
        self.groups: list[dict] | None = None  # override of the group-by answer
        self.total_override: int | None = None
        self.bump_after_page_calls: int | None = None
        self.requests: list[httpx.Request] = []
        self._page_calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.startswith("/api/views/"):
            meta = {"rowsUpdatedAt": self.updated_at, "columns": self.columns}
            return httpx.Response(200, json=meta)
        params = request.url.params
        if "$group" in params:
            if self.groups is not None:
                return httpx.Response(200, json=self.groups)
            if not self.rows:
                return httpx.Response(200, json=[])
            first = self.rows[0]
            count = self.total_override if self.total_override is not None else len(self.rows)
            return httpx.Response(
                200,
                json=[
                    {
                        "a_o_de_publicacion": first["a_o_de_publicacion"],
                        "mes_de_publicacion": first["mes_de_publicacion"],
                        "count": str(count),
                    }
                ],
            )
        self._page_calls += 1
        offset, limit = int(params["$offset"]), int(params["$limit"])
        body = json.dumps(self.rows[offset : offset + limit]).encode()
        if self.bump_after_page_calls == self._page_calls:
            self.updated_at += 1
        return httpx.Response(200, content=body)

    def client(self) -> SodaClient:
        return SodaClient(
            SodaSettings(base_url="https://example.test", app_token=None),
            transport=httpx.MockTransport(self.handler),
            sleep=lambda s: None,
            jitter=lambda: 0.0,
        )

    def page_params(self) -> list[httpx.QueryParams]:
        return [
            r.url.params
            for r in self.requests
            if r.url.path.startswith("/resource/") and "$group" not in r.url.params
        ]


class Clock:
    def __init__(self, first=datetime(2026, 10, 12, 12, 0, tzinfo=UTC)):
        self.t = first

    def __call__(self):
        self.t += timedelta(seconds=10)
        return self.t


def run(fake, store, *, force=False, batch_id=B1, page_size=3, clock=None):
    return extract_runt(
        fake.client(),
        store,
        force=force,
        now=clock or Clock(),
        new_batch_id=lambda: batch_id,
        extractor_version="0.0.1",
        page_size=page_size,
    )


def rows(n: int) -> list[dict]:
    return [row(i) for i in range(n)]


def test_commits_pages_and_manifest_last():
    store = MemoryRawStore()
    fake = FakeRunt(rows(7))
    result = run(fake, store)
    m = result.manifest
    assert result.outcome == "committed" and result.publication == "2026-10"
    prefix = batch_prefix(SOURCE_SYSTEM, date(2026, 10, 12), B1)
    assert [f.key for f in m.files] == [f"{prefix}payload-0000{i}.json" for i in range(3)]
    assert [(f.offset, f.row_count) for f in m.files] == [(0, 3), (3, 3), (6, 1)]
    for f in m.files:
        body = store.get(f.key)
        assert f.sha256 == sha256_hex(body) and f.size_bytes == len(body)
    assert result.manifest_key == manifest_key(prefix)
    assert list(store.objects)[-1] == result.manifest_key
    assert Manifest.from_json(store.get(result.manifest_key)) == m
    wm = m.watermark
    assert (wm.column, wm.mode, wm.from_exclusive, wm.to_observed) == (
        "a_o_de_publicacion,mes_de_publicacion",
        "full",
        None,
        date(2026, 10, 1),
    )
    assert m.source_rows_updated_at == 100 and m.row_count == 7
    assert m.dataset_id == DATASET_ID and m.query.where is None and m.query.order == ORDER
    assert all(p["$order"] == ":id ASC" for p in fake.page_params())
    assert [p["$offset"] for p in fake.page_params()] == ["0", "3", "6"]


def test_exact_multiple_of_page_size_does_not_write_empty_page():
    store = MemoryRawStore()
    result = run(FakeRunt(rows(6)), store)
    assert len(result.manifest.files) == 2


def test_schema_change_is_permanent_and_writes_nothing():
    store = MemoryRawStore()
    fake = FakeRunt(rows(3))
    fake.columns = COLUMNS[:-1] + [{"fieldName": "a_o_de_publicacion", "dataTypeName": "text"}]
    with pytest.raises(ExtractPermanentError, match="Schema drift"):
        run(fake, store)
    assert store.objects == {}
    assert fake.page_params() == []


def test_extra_column_is_schema_drift():
    fake = FakeRunt(rows(3))
    fake.columns = COLUMNS + [{"fieldName": "nueva", "dataTypeName": "text"}]
    with pytest.raises(ExtractPermanentError, match="Schema drift"):
        run(fake, MemoryRawStore())


def test_two_publications_is_permanent():
    store = MemoryRawStore()
    fake = FakeRunt(rows(3))
    fake.groups = [
        {"a_o_de_publicacion": "2026", "mes_de_publicacion": "OCTUBRE", "count": "2"},
        {"a_o_de_publicacion": "2026", "mes_de_publicacion": "SEPTIEMBRE", "count": "1"},
    ]
    with pytest.raises(ExtractPermanentError, match="exactly 1 publication"):
        run(fake, store)
    assert store.objects == {}


def test_truncation_is_transient_and_leaves_no_manifest():
    store = MemoryRawStore()
    fake = FakeRunt(rows(5))
    fake.total_override = 8
    with pytest.raises(ExtractTransientError, match="Truncated"):
        run(fake, store)
    assert not any(k.endswith("manifest.json") for k in store.objects)
    assert find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID) is None


def test_more_rows_than_expected_is_transient():
    fake = FakeRunt(rows(5))
    fake.total_override = 4
    with pytest.raises(ExtractTransientError):
        run(fake, MemoryRawStore())


def test_rows_updated_at_change_during_run_is_transient():
    store = MemoryRawStore()
    fake = FakeRunt(rows(5))
    fake.bump_after_page_calls = 1
    with pytest.raises(ExtractTransientError, match="rowsUpdatedAt changed"):
        run(fake, store)
    assert store.objects  # payloads written
    assert not any(k.endswith("manifest.json") for k in store.objects)


def test_unchanged_writes_nothing():
    store = MemoryRawStore()
    first = run(FakeRunt(rows(4)), store)
    before = dict(store.objects)
    fake = FakeRunt(rows(4))
    second = run(fake, store, batch_id=B2, clock=Clock(datetime(2026, 10, 13, 9, tzinfo=UTC)))
    assert second.outcome == "unchanged"
    assert second.manifest == first.manifest and second.manifest_key == first.manifest_key
    assert store.objects == before
    assert fake.page_params() == []


def test_changed_rows_updated_at_creates_new_batch():
    store = MemoryRawStore()
    run(FakeRunt(rows(4)), store)
    result = run(
        FakeRunt(rows(4), updated_at=101),
        store,
        batch_id=B2,
        clock=Clock(datetime(2026, 10, 13, 9, tzinfo=UTC)),
    )
    assert result.outcome == "committed" and result.manifest.batch_id == B2
    latest = find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID)
    assert latest is not None and latest.batch_id == B2


def test_force_creates_batch_even_if_unchanged():
    store = MemoryRawStore()
    run(FakeRunt(rows(4)), store)
    result = run(
        FakeRunt(rows(4)),
        store,
        force=True,
        batch_id=B2,
        clock=Clock(datetime(2026, 10, 13, 9, tzinfo=UTC)),
    )
    assert result.outcome == "committed" and result.manifest.batch_id == B2
    latest = find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID)
    assert latest is not None and latest.batch_id == B2


def test_unknown_month_in_group_query_is_permanent():
    fake = FakeRunt([row(0, mes_de_publicacion="OCTUBREX")])
    with pytest.raises(ExtractPermanentError, match="known month"):
        run(fake, MemoryRawStore())


def test_unknown_month_in_a_row_is_permanent():
    store = MemoryRawStore()
    data = rows(4)
    data[2] = row(2, mes_de_publicacion="Octubre")
    with pytest.raises(ExtractPermanentError, match="known month"):
        run(FakeRunt(data), store, page_size=10)
    assert store.objects == {}


def test_page_over_8_mib_is_permanent():
    store = MemoryRawStore()
    big = [row(i, nombre_municipio="X" * (3 * 1024 * 1024)) for i in range(3)]
    with pytest.raises(ExtractPermanentError, match="byte limit"):
        run(FakeRunt(big), store, page_size=3)
    assert store.objects == {}


def bad_rows():
    base = row(0)
    missing = {k: v for k, v in base.items() if k != "cantidad"}
    return {
        "missing_key": missing,
        "extra_key": {**base, "extra": "1"},
        "non_string_cantidad": {**base, "cantidad": 3},
        "null_value": {**base, "nombre_municipio": None},
        "cantidad_zero": row(0, cantidad="0"),
        "cantidad_negative": row(0, cantidad="-1"),
        "cantidad_decimal": row(0, cantidad="1.5"),
        "cantidad_empty": row(0, cantidad=""),
        "registro_future": row(0, fecha_de_registro="2027"),
        "registro_short": row(0, fecha_de_registro="99"),
        "registro_text": row(0, fecha_de_registro="abcd"),
    }


@pytest.mark.parametrize("name", sorted(bad_rows()))
def test_invalid_row_is_permanent_and_writes_nothing(name):
    store = MemoryRawStore()
    data = [row(0), row(1), bad_rows()[name]]
    fake = FakeRunt(data)
    fake.groups = [{"a_o_de_publicacion": "2026", "mes_de_publicacion": "OCTUBRE", "count": "3"}]
    with pytest.raises(ExtractPermanentError):
        run(fake, store, page_size=10)
    assert store.objects == {}


def test_row_from_another_publication_is_permanent():
    fake = FakeRunt([row(0), row(1, a_o_de_publicacion="2025")])
    fake.groups = [{"a_o_de_publicacion": "2026", "mes_de_publicacion": "OCTUBRE", "count": "2"}]
    with pytest.raises(ExtractPermanentError, match="another publication"):
        run(fake, MemoryRawStore(), page_size=10)


def test_registro_equal_to_publication_year_is_valid():
    result = run(FakeRunt([row(0, fecha_de_registro="2026")]), MemoryRawStore())
    assert result.manifest.row_count == 1


def _group(**over):
    base = {"a_o_de_publicacion": "2026", "mes_de_publicacion": "OCTUBRE", "count": "3"}
    return {**base, **over}


@pytest.mark.parametrize(
    "groups",
    [
        [],
        [{"a_o_de_publicacion": "2026", "mes_de_publicacion": "OCTUBRE"}],
        [{**_group(), "extra": "1"}],
        [_group(count="0")],
        [_group(count="abc")],
        [_group(count="-3")],
        [_group(count=3)],
        [_group(count=None)],
        [_group(a_o_de_publicacion="26")],
        [_group(a_o_de_publicacion="20266")],
        [_group(a_o_de_publicacion=2026)],
        [_group(a_o_de_publicacion="abcd")],
    ],
    ids=lambda g: repr(g)[:60],
)
def test_invalid_publication_group_is_permanent(groups):
    store = MemoryRawStore()
    fake = FakeRunt(rows(3))
    fake.groups = groups
    with pytest.raises(ExtractPermanentError):
        run(fake, store)
    assert store.objects == {}
    assert fake.page_params() == []


def test_empty_dataset_is_permanent():
    store = MemoryRawStore()
    with pytest.raises(ExtractPermanentError, match="exactly 1 publication"):
        run(FakeRunt([]), store)
    assert store.objects == {}


def _corrupt_previous(store):
    key = f"{batch_prefix(SOURCE_SYSTEM, date(2026, 10, 12), B1)}manifest.json"
    store.put_once(key, b"{not json", "application/json")
    return key


def test_corrupt_previous_manifest_fails_without_writes_and_without_force():
    store = MemoryRawStore()
    _corrupt_previous(store)
    before = dict(store.objects)
    fake = FakeRunt(rows(3))
    with pytest.raises(ExtractPermanentError):
        run(fake, store, batch_id=B2)
    assert store.objects == before
    assert fake.page_params() == []


def test_force_bypasses_corrupt_manifest_and_next_run_works():
    store = MemoryRawStore()
    _corrupt_previous(store)
    later = Clock(datetime(2026, 10, 13, 9, tzinfo=UTC))
    forced = run(FakeRunt(rows(3)), store, force=True, batch_id=B2, clock=later)
    assert forced.outcome == "committed"
    # The new batch lives in a newer partition, so the corrupt one is never read again.
    again = run(
        FakeRunt(rows(3)),
        store,
        batch_id="2d8b8e30-5e3c-4b20-9c73-4f6e8bafbc32",
        clock=Clock(datetime(2026, 10, 13, 15, tzinfo=UTC)),
    )
    assert again.outcome == "unchanged" and again.manifest.batch_id == B2


def test_trm_batch_with_same_rows_updated_at_is_not_unchanged():
    store = MemoryRawStore()
    trm = extract_trm(
        FakeSoda(make_rows(3), updated_at=100).client(),
        store,
        mode="full",
        since=None,
        now=Clock(),
        new_batch_id=lambda: B1,
        extractor_version="0.0.1",
    )
    assert trm.manifest.source_rows_updated_at == 100
    result = run(FakeRunt(rows(3), updated_at=100), store, batch_id=B2)
    assert result.outcome == "committed" and result.manifest.source_system == SOURCE_SYSTEM


def test_recovery_after_failure_with_orphan_payloads():
    store = MemoryRawStore()
    failing = FakeRunt(rows(5))
    failing.bump_after_page_calls = 1
    with pytest.raises(ExtractTransientError):
        run(failing, store, batch_id=B1)
    orphans = set(store.objects)
    assert orphans and find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID) is None

    result = run(FakeRunt(rows(5)), store, batch_id=B2)
    assert result.outcome == "committed"
    latest = find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID)
    assert latest is not None and latest.batch_id == B2
    assert orphans <= set(store.objects)  # orphans are left untouched (write-once)

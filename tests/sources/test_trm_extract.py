"""Offline tests for the TRM extractor (httpx.MockTransport + MemoryRawStore)."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from pits.ingestion.manifest import Manifest, find_latest_committed, manifest_key, sha256_hex
from pits.ingestion.raw_store import (
    MemoryRawStore,
    RawObjectExistsError,
    RawStoreError,
    RawStoreTransientError,
    batch_prefix,
)
from pits.sources.soda.client import SodaClient
from pits.sources.soda.settings import SodaSettings
from pits.sources.trm.contract import BACKFILL_FROM, DATASET_ID, ORDER, SOURCE_SYSTEM
from pits.sources.trm.extract import (
    ExtractError,
    ExtractPermanentError,
    ExtractTransientError,
    ExtractUsageError,
    extract_trm,
)

B1 = "0b6f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a10"
B2 = "1c7a7d2f-4d2b-4a1f-8b62-3e5d7a9fab21"
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


class Clock:
    def __init__(self, first=datetime(2026, 10, 10, 12, 0, tzinfo=UTC)):
        self.t = first

    def __call__(self):
        self.t += timedelta(seconds=10)
        return self.t


def run(fake, store, *, mode="full", since=None, batch_id=B1, page_size=3, clock=None):
    return extract_trm(
        fake.client(),
        store,
        mode=mode,
        since=since,
        now=clock or Clock(),
        new_batch_id=lambda: batch_id,
        extractor_version="0.0.1",
        page_size=page_size,
    )


def full_batch(store, rows=None, batch_id=B1, clock=None):
    """Commit a full batch so later incremental runs have a watermark."""
    fake = FakeSoda(rows if rows is not None else make_rows(7))
    return run(fake, store, batch_id=batch_id, clock=clock)


def test_backfill_writes_pages_and_manifest_last():
    store = MemoryRawStore()
    fake = FakeSoda(make_rows(7))
    result = run(fake, store)
    m = result.manifest
    prefix = batch_prefix(SOURCE_SYSTEM, date(2026, 10, 10), B1)
    assert [f.key for f in m.files] == [f"{prefix}payload-0000{i}.json" for i in range(3)]
    assert [(f.offset, f.row_count) for f in m.files] == [(0, 3), (3, 3), (6, 1)]
    assert m.row_count == 7
    for f in m.files:
        body = store.get(f.key)
        assert f.sha256 == sha256_hex(body) and f.size_bytes == len(body)
        assert store.content_types[f.key] == "application/json"
    assert result.manifest_key == manifest_key(prefix)
    assert list(store.objects)[-1] == result.manifest_key  # written last
    assert Manifest.from_json(store.get(result.manifest_key)) == m
    wm = m.watermark
    assert (wm.mode, wm.from_exclusive, wm.to_observed) == ("full", None, START + timedelta(6))
    assert m.query.where is None and m.query.order == ORDER and m.query.page_size == 3
    assert m.source_rows_updated_at == 100 and m.app_token_used is False
    assert m.extraction_date == date(2026, 10, 10)
    assert m.extractor.version == "0.0.1"
    assert [p["$offset"] for p in fake.resource_params()] == ["0", "3", "6"]
    assert all(p["$order"] == ORDER and p["$limit"] == "3" for p in fake.resource_params())


def test_exact_multiple_of_page_size_does_not_write_empty_page():
    store = MemoryRawStore()
    result = run(FakeSoda(make_rows(6)), store)
    assert len(result.manifest.files) == 2
    assert sum(1 for k in store.objects if "payload-" in k) == 2


def test_incremental_reads_after_watermark():
    store = MemoryRawStore()
    first = full_batch(store, make_rows(7))
    fake = FakeSoda(make_rows(10))
    result = run(
        fake,
        store,
        mode="incremental",
        batch_id=B2,
        clock=Clock(datetime(2026, 10, 11, 9, tzinfo=UTC)),
    )
    m = result.manifest
    watermark = first.manifest.watermark.to_observed
    assert m.query.where == f"vigenciadesde > '{watermark.isoformat()}T00:00:00.000'"
    assert fake.resource_params()[0]["$where"] == m.query.where
    wm = m.watermark
    assert (wm.mode, wm.from_exclusive, wm.to_observed) == (
        "incremental",
        watermark,
        START + timedelta(9),
    )
    assert m.row_count == 3


def test_incremental_without_previous_batch_behaves_as_full_backfill():
    store = MemoryRawStore()
    result = run(FakeSoda(make_rows(4)), store, mode="incremental")
    assert result.manifest.watermark.mode == "full"
    assert result.manifest.watermark.from_exclusive is None
    assert result.manifest.query.where is None
    assert result.manifest.row_count == 4


def test_incremental_empty_carries_watermark_forward():
    store = MemoryRawStore()
    first = full_batch(store, make_rows(7))
    result = run(FakeSoda(make_rows(7)), store, mode="incremental", batch_id=B2)
    m = result.manifest
    assert m.row_count == 0 and m.files == ()
    assert m.watermark.to_observed == first.manifest.watermark.to_observed
    assert m.watermark.from_exclusive == m.watermark.to_observed
    assert store.get(result.manifest_key)  # evidence of the run was committed
    assert not [k for k in store.objects if "payload-" in k and B2 in k]


def test_since_uses_inclusive_where_and_previous_day_as_from_exclusive():
    store = MemoryRawStore()
    full_batch(store, make_rows(7))
    since = START + timedelta(4)
    fake = FakeSoda(make_rows(9))
    result = run(fake, store, mode="since", since=since, batch_id=B2)
    m = result.manifest
    assert m.query.where == f"vigenciadesde >= '{since.isoformat()}T00:00:00.000'"
    assert m.watermark.mode == "since"
    assert m.watermark.from_exclusive == since - timedelta(days=1)
    assert m.watermark.to_observed == START + timedelta(8)
    assert m.row_count == 5


def test_since_empty_without_previous_batch_has_no_watermark():
    result = run(FakeSoda([]), MemoryRawStore(), mode="since", since=BACKFILL_FROM)
    assert result.manifest.row_count == 0 and result.manifest.watermark.to_observed is None


def test_since_empty_keeps_previous_watermark():
    store = MemoryRawStore()
    first = full_batch(store, make_rows(7))
    since = first.manifest.watermark.to_observed + timedelta(days=1)  # nothing newer exists
    after = run(FakeSoda(make_rows(7)), store, mode="since", since=since, batch_id=B2)
    assert after.manifest.row_count == 0
    assert after.manifest.watermark.to_observed == first.manifest.watermark.to_observed


def test_since_gap_guard_with_previous_batch():
    store = MemoryRawStore()
    first = full_batch(store, make_rows(7))
    gap = first.manifest.watermark.to_observed + timedelta(days=2)
    with pytest.raises(ExtractUsageError, match="leave a gap"):
        run(FakeSoda(make_rows(7)), store, mode="since", since=gap, batch_id=B2)


def test_since_gap_guard_without_previous_batch():
    store = MemoryRawStore()
    with pytest.raises(ExtractUsageError, match="leave a gap"):
        run(FakeSoda(make_rows(3)), store, mode="since", since=date(2027, 1, 1))
    assert store.objects == {}


def test_full_empty_is_transient_and_writes_no_manifest():
    store = MemoryRawStore()
    with pytest.raises(ExtractTransientError, match="no rows"):
        run(FakeSoda([]), store)
    assert store.objects == {}


def test_schema_change_in_metadata_is_permanent_with_zero_writes():
    store = MemoryRawStore()
    changed = [*COLUMNS[:3], {"fieldName": "vigenciahasta", "dataTypeName": "text"}]
    with pytest.raises(ExtractPermanentError, match="Schema drift"):
        run(FakeSoda(make_rows(3), columns=changed), store)
    extra = [*COLUMNS, {"fieldName": "nueva", "dataTypeName": "text"}]
    with pytest.raises(ExtractPermanentError, match="Schema drift"):
        run(FakeSoda(make_rows(3), columns=extra), store)
    assert store.objects == {}


def test_system_columns_in_metadata_are_ignored():
    columns = [*COLUMNS, {"fieldName": ":id", "dataTypeName": "meta_data"}]
    assert run(FakeSoda(make_rows(3), columns=columns), MemoryRawStore()).manifest.row_count == 3


def bad_rows_cases():
    extra = make_rows(3)
    extra[1]["extra"] = "x"
    missing = make_rows(3)
    del missing[2]["unidad"]
    hour = make_rows(3)
    hour[0]["vigenciadesde"] = "2026-01-01T05:30:00.000"
    dup = make_rows(3)
    dup[2] = dict(dup[1])
    unordered = make_rows(3)
    unordered[1], unordered[2] = unordered[2], unordered[1]
    non_string = make_rows(3)
    non_string[0]["valor"] = 3900.5
    return [
        pytest.param(extra, "wrong keys", id="extra-key"),
        pytest.param(missing, "wrong keys", id="missing-key"),
        pytest.param(hour, "midnight", id="time-not-midnight"),
        pytest.param(dup, "duplicated or out of order", id="duplicate"),
        pytest.param(unordered, "duplicated or out of order", id="unordered"),
        pytest.param(non_string, "must be a string", id="non-string-valor"),
    ]


@pytest.mark.parametrize(("rows", "message"), bad_rows_cases())
def test_invalid_rows_are_permanent_without_manifest(rows, message):
    store = MemoryRawStore()
    with pytest.raises(ExtractPermanentError, match=message):
        run(FakeSoda(rows), store, page_size=10)
    assert not any(k.endswith("manifest.json") for k in store.objects)


def test_order_is_enforced_across_pages():
    rows = make_rows(6)
    rows[3] = row(START)  # page 2 starts before page 1 ended
    store = MemoryRawStore()
    with pytest.raises(ExtractPermanentError, match="duplicated or out of order"):
        run(FakeSoda(rows), store)
    assert not any(k.endswith("manifest.json") for k in store.objects)


def test_row_not_after_watermark_is_permanent():
    store = MemoryRawStore()
    full_batch(store, make_rows(7))

    class Leaky(FakeSoda):
        def handler(self, request):
            if request.url.path.startswith("/resource/"):
                self.requests.append(request)
                return httpx.Response(200, content=json.dumps(self.rows[:1]).encode())
            return super().handler(request)

    with pytest.raises(ExtractPermanentError, match="not after the watermark"):
        run(Leaky(make_rows(7)), store, mode="incremental", batch_id=B2)


def test_rows_updated_at_change_is_transient_without_manifest():
    store = MemoryRawStore()
    fake = FakeSoda(make_rows(7))
    fake.bump_after_resource_calls = 2
    with pytest.raises(ExtractTransientError, match="rowsUpdatedAt"):
        run(fake, store)
    assert not any(k.endswith("manifest.json") for k in store.objects)
    assert find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID) is None


def test_soda_503_exhausted_is_transient():
    fake = FakeSoda(make_rows(3))
    fake.resource_status = 503
    store = MemoryRawStore()
    with pytest.raises(ExtractTransientError, match="503"):
        run(fake, store)
    assert store.objects == {}


def test_soda_404_is_permanent():
    fake = FakeSoda(make_rows(3))
    fake.resource_status = 404
    with pytest.raises(ExtractPermanentError, match="404"):
        run(fake, MemoryRawStore())


def test_two_runs_same_day_use_distinct_batches_without_conflict():
    store = MemoryRawStore()
    fake = FakeSoda(make_rows(4))
    first = run(fake, store, batch_id=B1)
    second = run(fake, store, batch_id=B2)
    assert first.manifest.batch_id != second.manifest.batch_id
    assert first.manifest_key != second.manifest_key
    assert find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID) == second.manifest


def test_repeated_batch_id_is_permanent_write_conflict():
    store = MemoryRawStore()
    fake = FakeSoda(make_rows(4))
    run(fake, store, batch_id=B1)
    with pytest.raises(ExtractPermanentError, match="already exists") as err:
        run(fake, store, batch_id=B1)
    assert isinstance(err.value.__cause__, RawObjectExistsError)


def test_extraction_date_is_utc_date_of_start():
    late = Clock(datetime(2026, 10, 10, 23, 59, 59, tzinfo=UTC))
    result = run(FakeSoda(make_rows(2)), MemoryRawStore(), clock=late)
    assert result.manifest.started_at.date() == date(2026, 10, 11)
    assert result.manifest.extraction_date == date(2026, 10, 11)


def test_mode_since_argument_consistency():
    with pytest.raises(ExtractUsageError, match="since"):
        run(FakeSoda(make_rows(2)), MemoryRawStore(), mode="since", since=None)
    with pytest.raises(ExtractUsageError, match="since"):
        run(FakeSoda(make_rows(2)), MemoryRawStore(), mode="full", since=START)


def test_error_hierarchy():
    for cls in (ExtractPermanentError, ExtractTransientError, ExtractUsageError):
        assert issubclass(cls, ExtractError)


class FailingStore(MemoryRawStore):
    def __init__(self, error):
        super().__init__()
        self.error = error

    def put_once(self, key, body, content_type):
        raise self.error


def test_transient_store_error_maps_to_transient():
    store = FailingStore(RawStoreTransientError("put_object failed: ConnectTimeoutError"))
    with pytest.raises(ExtractTransientError, match="ConnectTimeoutError"):
        run(FakeSoda(make_rows(3)), store)


def test_other_store_error_maps_to_permanent():
    store = FailingStore(RawStoreError("Object 'k' is 9 bytes, above the 8 byte limit"))
    with pytest.raises(ExtractPermanentError, match="byte limit"):
        run(FakeSoda(make_rows(3)), store)


@pytest.mark.parametrize(
    "meta",
    [
        pytest.param({"rowsUpdatedAt": 1}, id="no-columns"),
        pytest.param({"rowsUpdatedAt": 1, "columns": "x"}, id="columns-not-list"),
        pytest.param({"rowsUpdatedAt": 1, "columns": ["x"]}, id="columns-not-objects"),
        pytest.param({"columns": COLUMNS}, id="no-rows-updated-at"),
        pytest.param({"columns": COLUMNS, "rowsUpdatedAt": True}, id="rows-updated-at-bool"),
        pytest.param({"columns": COLUMNS, "rowsUpdatedAt": "1"}, id="rows-updated-at-str"),
    ],
)
def test_malformed_metadata_is_permanent_with_zero_writes(meta):
    fake = FakeSoda(make_rows(3))
    fake.meta_override = meta
    store = MemoryRawStore()
    with pytest.raises(ExtractPermanentError):
        run(fake, store)
    assert store.objects == {}


def test_impossible_calendar_date_is_permanent():
    rows = make_rows(3)
    rows[1]["vigenciadesde"] = "2026-02-30T00:00:00.000"
    with pytest.raises(ExtractPermanentError, match="not a valid date"):
        run(FakeSoda(rows), MemoryRawStore(), page_size=10)


def test_invalid_vigenciahasta_is_permanent():
    rows = make_rows(3)
    rows[0]["vigenciahasta"] = "2026-01-01"
    with pytest.raises(ExtractPermanentError, match="vigenciahasta"):
        run(FakeSoda(rows), MemoryRawStore(), page_size=10)


@pytest.mark.parametrize("valor", ["abc", "", "NaN", "Infinity"])
def test_non_numeric_valor_is_permanent(valor):
    rows = make_rows(3)
    rows[1]["valor"] = valor
    with pytest.raises(ExtractPermanentError, match="valor"):
        run(FakeSoda(rows), MemoryRawStore(), page_size=10)


def test_requests_match_literal_contract():
    fake = FakeSoda(make_rows(4))
    run(fake, MemoryRawStore())
    paths = [r.url.path for r in fake.requests]
    assert paths[0] == "/api/views/32sa-8pi3.json"
    assert paths[-1] == "/api/views/32sa-8pi3.json"
    assert set(paths[1:-1]) == {"/resource/32sa-8pi3.json"}
    for params in fake.resource_params():
        assert params["$order"] == "vigenciadesde ASC, :id ASC"
        assert "$where" not in params
    assert ORDER == "vigenciadesde ASC, :id ASC"


def test_token_flag_recorded_in_manifest_and_token_never_stored():
    fake = FakeSoda(make_rows(4))
    fake.token = "s3cr3t-token-value"
    store = MemoryRawStore()
    result = run(fake, store)
    assert result.manifest.app_token_used is True
    assert all(b"s3cr3t-token-value" not in body for body in store.objects.values())
    assert run(FakeSoda(make_rows(4)), MemoryRawStore()).manifest.app_token_used is False


def test_same_inputs_in_separate_stores_give_identical_manifest_bytes():
    first, second = MemoryRawStore(), MemoryRawStore()
    a = run(FakeSoda(make_rows(7)), first)
    b = run(FakeSoda(make_rows(7)), second)
    assert first.get(a.manifest_key) == second.get(b.manifest_key)
    assert first.objects == second.objects


def test_finished_at_never_before_started_at():
    times = iter([datetime(2026, 10, 10, 12, tzinfo=UTC), datetime(2026, 10, 10, 11, tzinfo=UTC)])
    result = run(FakeSoda(make_rows(2)), MemoryRawStore(), clock=lambda: next(times))
    assert result.manifest.finished_at == result.manifest.started_at

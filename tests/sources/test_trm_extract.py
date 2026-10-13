"""Offline tests for the TRM extractor (httpx.MockTransport + MemoryRawStore)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from soda_support import COLUMNS, START, FakeSoda, make_rows, row

from pits.ingestion.manifest import Manifest, find_latest_committed, manifest_key, sha256_hex
from pits.ingestion.raw_store import (
    MemoryRawStore,
    RawObjectConflictError,
    RawObjectExistsError,
    RawStoreError,
    RawStoreTransientError,
    batch_prefix,
)
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
            if request.url.path.startswith("/resource/") and "$select" not in request.url.params:
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


def test_repeated_batch_id_with_different_bytes_is_permanent_write_conflict():
    store = MemoryRawStore()
    fake = FakeSoda(make_rows(4))
    run(fake, store, batch_id=B1)
    before = dict(store.objects)
    later = Clock(datetime(2026, 10, 10, 13, 0, tzinfo=UTC))  # same day, different timestamps
    with pytest.raises(ExtractPermanentError, match="already exists") as err:
        run(fake, store, batch_id=B1, clock=later)
    assert isinstance(err.value.__cause__, RawObjectConflictError)
    assert isinstance(err.value.__cause__, RawObjectExistsError)
    assert store.objects == before  # nothing overwritten, nothing new


def test_repeated_batch_id_with_identical_bytes_succeeds_without_new_objects():
    store = MemoryRawStore()
    fake = FakeSoda(make_rows(4))
    first = run(fake, store, batch_id=B1)
    before = dict(store.objects)
    second = run(fake, store, batch_id=B1)  # same clock and data -> same bytes
    assert second.manifest == first.manifest
    assert store.objects == before


class LostResponseStore(MemoryRawStore):
    """Stores the object, then fails the response with 412 once (lost-response retry)."""

    def __init__(self):
        super().__init__()
        self.lost = 0

    def put_once(self, key, body, content_type):
        if key.endswith("payload-00001.json") and not self.lost:
            self.lost = 1
            super().put_once(key, body, content_type)
            # the client retries internally: the object now exists with our own bytes
        return super().put_once(key, body, content_type)


def test_lost_response_then_412_still_commits():
    store = LostResponseStore()
    result = run(FakeSoda(make_rows(7)), store)
    assert store.lost == 1
    assert find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID) == result.manifest


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


def _no_manifest(store):
    return not any(k.endswith("manifest.json") for k in store.objects)


@pytest.mark.parametrize("mode", ["full", "incremental", "since"])
def test_count_guard_runs_after_metadata_and_before_pages_with_same_where(mode):
    store = MemoryRawStore()
    kwargs = {}
    if mode == "full":
        fake = FakeSoda(make_rows(10))
    else:
        full_batch(store, make_rows(7))
        fake = FakeSoda(make_rows(10))
        kwargs = {"mode": mode, "batch_id": B2}
        if mode == "since":
            kwargs["since"] = START + timedelta(4)
    result = run(fake, store, **kwargs)
    paths = [(r.url.path, r.url.params.get("$select")) for r in fake.requests]
    assert paths[0][0].startswith("/api/views/")
    assert paths[1] == ("/resource/32sa-8pi3.json", "count(*)")
    assert all(sel is None for _, sel in paths[2:-1])
    (count,) = fake.count_params()
    where = result.manifest.query.where
    if mode == "full":
        assert where is None and dict(count) == {"$select": "count(*)"}
    else:
        assert where.startswith("vigenciadesde >" + ("=" if mode == "since" else ""))
        assert dict(count) == {"$select": "count(*)", "$where": where}


def test_short_page_before_total_is_transient_truncated_without_manifest():
    store = MemoryRawStore()
    fake = FakeSoda(make_rows(7))
    fake.count_override = "10"  # source announced 10 rows but pages end at 7
    with pytest.raises(ExtractTransientError, match="Truncated extraction: read 7 .* expected 10"):
        run(fake, store)
    assert _no_manifest(store)


def test_more_rows_than_count_is_transient_without_manifest():
    store = MemoryRawStore()
    fake = FakeSoda(make_rows(7))
    fake.count_override = "5"
    with pytest.raises(
        ExtractTransientError, match="Truncated extraction: page at offset 3 exceeds the expected 5"
    ):
        run(fake, store)
    assert _no_manifest(store)


@pytest.mark.parametrize(
    "response",
    [
        pytest.param([], id="no-rows"),
        pytest.param([{"count": "1"}, {"count": "1"}], id="two-rows"),
        pytest.param([{"count": "1", "extra": "x"}], id="extra-key"),
        pytest.param([{"total": "1"}], id="wrong-key"),
        pytest.param([{"count": 5}], id="int-not-string"),
        pytest.param([{"count": "abc"}], id="not-numeric"),
        pytest.param([{"count": "-1"}], id="negative"),
        pytest.param([{"count": ""}], id="empty"),
    ],
)
def test_malformed_count_is_permanent_with_zero_writes(response):
    store = MemoryRawStore()
    fake = FakeSoda(make_rows(3))
    fake.count_response_rows = response
    with pytest.raises(ExtractPermanentError, match="[Cc]ount"):
        run(fake, store)
    assert store.objects == {}
    assert fake.resource_params() == []  # no page was requested


def test_incremental_with_count_zero_commits_an_empty_batch():
    store = MemoryRawStore()
    first = full_batch(store, make_rows(7))
    fake = FakeSoda(make_rows(7))
    result = run(fake, store, mode="incremental", batch_id=B2)
    assert fake.count_params()[0]["$select"] == "count(*)"
    assert result.manifest.row_count == 0 and result.manifest.files == ()
    assert result.manifest.watermark.to_observed == first.manifest.watermark.to_observed
    assert store.get(result.manifest_key)

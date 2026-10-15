"""Offline tests for the regional brand fleet extractor (httpx.MockTransport + MemoryRawStore)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from brand_fleet_support import (
    B1,
    B2,
    BOYACA,
    RISARALDA,
    ROWS_UPDATED_AT,
    ROWS_UPDATED_DATE,
    Clock,
    FakeBrandFleet,
    boyaca_row,
    columns,
    risaralda_row,
)

from pits.ingestion.manifest import Manifest, find_latest_committed, manifest_key, sha256_hex
from pits.ingestion.raw_store import MemoryRawStore, batch_prefix
from pits.sources.brand_fleet.contract import ORDER, SOURCES
from pits.sources.brand_fleet.extract import extract_brand_fleet
from pits.sources.extract_common import ExtractPermanentError, ExtractTransientError

NEXT_DAY = datetime(2026, 10, 15, 9, tzinfo=UTC)


def boyaca(n: int) -> list[dict]:
    return [boyaca_row(i) for i in range(n)]


def risaralda(n: int) -> list[dict]:
    return [risaralda_row(i) for i in range(n)]


def run(fake, store, *, force=False, batch_id=B1, page_size=3, clock=None):
    return extract_brand_fleet(
        fake.client(),
        store,
        fake.source,
        force=force,
        now=clock or Clock(),
        new_batch_id=lambda: batch_id,
        extractor_version="0.0.1",
        page_size=page_size,
    )


def test_contract_shapes():
    assert BOYACA.requested_schema == BOYACA.source_schema and len(BOYACA.source_schema) == 18
    assert len(RISARALDA.source_schema) == 6
    assert [c.name for c in RISARALDA.requested_schema] == [
        "clase",
        "marca",
        "modelo",
        "linea",
        "cilindraje",
    ]
    assert RISARALDA.select == "clase,marca,modelo,linea,cilindraje"
    assert {s.source_system for s in SOURCES.values()} == {
        "gobernacion_boyaca_parque_automotor",
        "gobernacion_risaralda_parque_automotor",
    }


def test_commits_pages_and_manifest_last():
    store = MemoryRawStore()
    fake = FakeBrandFleet(BOYACA, boyaca(7))
    result = run(fake, store)
    m = result.manifest
    assert result.outcome == "committed" and result.rows_updated == "2026-07-06"
    prefix = batch_prefix(BOYACA.source_system, date(2026, 10, 14), B1)
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
        "rowsUpdatedAt",
        "full",
        None,
        ROWS_UPDATED_DATE,
    )
    assert m.source_rows_updated_at == ROWS_UPDATED_AT and m.row_count == 7
    assert m.dataset_id == "em3d-hmim" and m.query.where is None and m.query.order == ORDER
    assert [p["$offset"] for p in fake.page_params()] == ["0", "3", "6"]


@pytest.mark.parametrize("source", [BOYACA, RISARALDA], ids=lambda s: s.key)
def test_select_is_derived_from_contract_and_count_has_none(source):
    data = boyaca(4) if source is BOYACA else risaralda(4)
    fake = FakeBrandFleet(source, data)
    result = run(fake, MemoryRawStore())
    assert result.manifest.schema == source.requested_schema
    pages = fake.page_params()
    assert pages and all(p["$select"] == source.select for p in pages)
    assert all(p["$order"] == ":id ASC" for p in pages)
    counts = fake.count_requests()
    assert len(counts) == 1
    assert set(counts[0]) == {"$select"} and counts[0]["$select"] == "count(*)"


def test_risaralda_manifest_schema_has_no_plate():
    result = run(FakeBrandFleet(RISARALDA, risaralda(3)), MemoryRawStore())
    assert "placa" not in [c.name for c in result.manifest.schema]
    assert result.manifest.schema == RISARALDA.requested_schema


def test_null_keys_are_omitted_and_accepted():
    data = [
        {"clase": "AUTOMOVIL", "marca": "MARCA X", "linea": "L1"},
        {"clase": "AUTOMOVIL", "marca": "MARCA X", "linea": "L2", "modelo": "2010"},
    ]
    result = run(FakeBrandFleet(RISARALDA, data), MemoryRawStore())
    assert result.manifest.row_count == 2


def test_row_with_plate_is_permanent_and_writes_nothing():
    store = MemoryRawStore()
    data = risaralda(4)
    data[1] = {**data[1], "placa": "AAA000"}
    fake = FakeBrandFleet(RISARALDA, data, honour_select=False)  # a source that ignores $select
    with pytest.raises(ExtractPermanentError, match=r"row 1\.placa") as info:
        run(fake, store, page_size=10)
    assert "AAA000" not in str(info.value)
    assert store.objects == {}


def test_extra_key_is_permanent_and_writes_nothing():
    store = MemoryRawStore()
    data = boyaca(3)
    data[2] = {**data[2], "extra": "1"}
    with pytest.raises(ExtractPermanentError, match="row 2 has unexpected keys"):
        run(FakeBrandFleet(BOYACA, data, honour_select=False), store, page_size=10)
    assert store.objects == {}


def test_schema_drift_is_permanent_and_writes_nothing():
    store = MemoryRawStore()
    fake = FakeBrandFleet(BOYACA, boyaca(3))
    fake.columns = columns(BOYACA)[:-1]
    with pytest.raises(ExtractPermanentError, match="Schema drift"):
        run(fake, store)
    assert store.objects == {} and fake.page_params() == []


def test_risaralda_metadata_must_still_list_the_plate_column():
    fake = FakeBrandFleet(RISARALDA, risaralda(3))
    fake.columns = [c for c in columns(RISARALDA) if c["fieldName"] != "placa"]
    with pytest.raises(ExtractPermanentError, match="Schema drift"):
        run(fake, MemoryRawStore())


def test_truncation_is_transient_and_leaves_no_manifest():
    store = MemoryRawStore()
    fake = FakeBrandFleet(BOYACA, boyaca(5))
    fake.total_override = 8
    with pytest.raises(ExtractTransientError, match="Truncated"):
        run(fake, store)
    assert not any(k.endswith("manifest.json") for k in store.objects)
    assert find_latest_committed(store, BOYACA.source_system, BOYACA.dataset_id) is None


def test_more_rows_than_expected_is_transient():
    fake = FakeBrandFleet(BOYACA, boyaca(5))
    fake.total_override = 4
    with pytest.raises(ExtractTransientError):
        run(fake, MemoryRawStore())


def test_empty_dataset_count_zero_is_permanent():
    with pytest.raises(ExtractPermanentError, match="positive integer"):
        run(FakeBrandFleet(BOYACA, []), MemoryRawStore())


def test_rows_updated_at_change_during_run_is_transient():
    store = MemoryRawStore()
    fake = FakeBrandFleet(BOYACA, boyaca(5))
    fake.bump_after_page_calls = 1
    with pytest.raises(ExtractTransientError, match="rowsUpdatedAt changed"):
        run(fake, store)
    assert store.objects
    assert not any(k.endswith("manifest.json") for k in store.objects)


def test_unchanged_writes_nothing_and_reads_no_page():
    store = MemoryRawStore()
    first = run(FakeBrandFleet(BOYACA, boyaca(4)), store)
    before = dict(store.objects)
    fake = FakeBrandFleet(BOYACA, boyaca(4))
    second = run(fake, store, batch_id=B2, clock=Clock(NEXT_DAY))
    assert second.outcome == "unchanged"
    assert second.manifest == first.manifest and second.manifest_key == first.manifest_key
    assert store.objects == before
    assert fake.page_params() == []


def test_sources_do_not_share_unchanged_state():
    store = MemoryRawStore()
    run(FakeBrandFleet(BOYACA, boyaca(4)), store)
    result = run(FakeBrandFleet(RISARALDA, risaralda(4)), store, batch_id=B2)
    assert result.outcome == "committed"


def test_changed_rows_updated_at_creates_new_batch():
    store = MemoryRawStore()
    run(FakeBrandFleet(BOYACA, boyaca(4)), store)
    result = run(
        FakeBrandFleet(BOYACA, boyaca(4), updated_at=ROWS_UPDATED_AT + 86400 * 30),
        store,
        batch_id=B2,
        clock=Clock(NEXT_DAY),
    )
    assert result.outcome == "committed" and result.manifest.batch_id == B2
    latest = find_latest_committed(store, BOYACA.source_system, BOYACA.dataset_id)
    assert latest is not None and latest.batch_id == B2


def test_force_creates_batch_even_if_unchanged():
    store = MemoryRawStore()
    run(FakeBrandFleet(BOYACA, boyaca(4)), store)
    result = run(
        FakeBrandFleet(BOYACA, boyaca(4)), store, force=True, batch_id=B2, clock=Clock(NEXT_DAY)
    )
    assert result.outcome == "committed" and result.manifest.batch_id == B2


def test_page_over_8_mib_is_permanent():
    store = MemoryRawStore()
    big = [boyaca_row(i, municipio="X" * (3 * 1024 * 1024)) for i in range(3)]
    with pytest.raises(ExtractPermanentError, match="byte limit"):
        run(FakeBrandFleet(BOYACA, big), store, page_size=3)
    assert store.objects == {}


def test_naive_clock_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        extract_brand_fleet(
            FakeBrandFleet(BOYACA, boyaca(1)).client(),
            MemoryRawStore(),
            BOYACA,
            force=False,
            now=lambda: datetime(2026, 10, 14, 12),
            new_batch_id=lambda: B1,
            extractor_version="t",
        )


def bad_rows():
    b = boyaca_row(0)
    return {
        "missing_clase": {k: v for k, v in b.items() if k != "clase"},
        "missing_linea": {k: v for k, v in b.items() if k != "linea"},
        "missing_servicio": {k: v for k, v in b.items() if k != "servicio"},
        "missing_estado": {k: v for k, v in b.items() if k != "estado"},
        "non_string": {**b, "marca": 5},
        "null_value": {**b, "marca": None},
        "empty_marca": boyaca_row(0, marca=""),
        "control_nul": boyaca_row(0, linea="LI\x00NEA"),
        "control_c1": boyaca_row(0, municipio="TUN\x85JA"),
    }


@pytest.mark.parametrize("name", sorted(bad_rows()))
def test_invalid_boyaca_row_is_permanent_and_writes_nothing(name):
    store = MemoryRawStore()
    data = [boyaca_row(1), boyaca_row(2), bad_rows()[name]]
    with pytest.raises(ExtractPermanentError, match="row 2"):
        run(FakeBrandFleet(BOYACA, data, honour_select=False), store, page_size=10)
    assert store.objects == {}


def test_boyaca_optional_keys_may_be_absent():
    row = {k: v for k, v in boyaca_row(0).items() if k not in ("modelo", "cilindraje", "n")}
    assert run(FakeBrandFleet(BOYACA, [row]), MemoryRawStore()).manifest.row_count == 1


def test_risaralda_does_not_require_service_or_status():
    assert run(FakeBrandFleet(RISARALDA, risaralda(2)), MemoryRawStore()).manifest.row_count == 2

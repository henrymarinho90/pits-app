"""Offline tests for the DIVIPOLA extractor (httpx.MockTransport + MemoryRawStore)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from divipola_support import (
    B1,
    B2,
    COLUMNS,
    ROWS_UPDATED_AT,
    ROWS_UPDATED_DATE,
    Clock,
    FakeDivipola,
    raw_row,
    rows,
)

from pits.ingestion.manifest import Manifest, find_latest_committed, manifest_key, sha256_hex
from pits.ingestion.raw_store import MemoryRawStore, batch_prefix
from pits.sources.divipola.contract import DATASET_ID, ORDER, SOURCE_SYSTEM
from pits.sources.divipola.extract import extract_divipola
from pits.sources.extract_common import ExtractPermanentError, ExtractTransientError

NEXT_DAY = datetime(2026, 10, 14, 9, tzinfo=UTC)


def run(fake, store, *, force=False, batch_id=B1, page_size=3, clock=None):
    return extract_divipola(
        fake.client(),
        store,
        force=force,
        now=clock or Clock(),
        new_batch_id=lambda: batch_id,
        extractor_version="0.0.1",
        page_size=page_size,
    )


def test_commits_pages_and_manifest_last():
    store = MemoryRawStore()
    fake = FakeDivipola(rows(7))
    result = run(fake, store)
    m = result.manifest
    assert result.outcome == "committed" and result.rows_updated == "2025-01-24"
    prefix = batch_prefix(SOURCE_SYSTEM, date(2026, 10, 13), B1)
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
    assert m.dataset_id == DATASET_ID and m.query.where is None and m.query.order == ORDER
    assert all(p["$order"] == ":id ASC" for p in fake.page_params())
    assert [p["$offset"] for p in fake.page_params()] == ["0", "3", "6"]


def test_exact_multiple_of_page_size_does_not_write_empty_page():
    result = run(FakeDivipola(rows(6)), MemoryRawStore())
    assert len(result.manifest.files) == 2


def test_schema_drift_is_permanent_and_writes_nothing():
    store = MemoryRawStore()
    fake = FakeDivipola(rows(3))
    fake.columns = COLUMNS[:-1]
    with pytest.raises(ExtractPermanentError, match="Schema drift"):
        run(fake, store)
    assert store.objects == {} and fake.page_params() == []


def test_type_change_is_schema_drift():
    fake = FakeDivipola(rows(3))
    fake.columns = COLUMNS[:-1] + [{"fieldName": "latitud", "dataTypeName": "number"}]
    with pytest.raises(ExtractPermanentError, match="Schema drift"):
        run(fake, MemoryRawStore())


def test_truncation_is_transient_and_leaves_no_manifest():
    store = MemoryRawStore()
    fake = FakeDivipola(rows(5))
    fake.total_override = 8
    with pytest.raises(ExtractTransientError, match="Truncated"):
        run(fake, store)
    assert not any(k.endswith("manifest.json") for k in store.objects)
    assert find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID) is None


def test_more_rows_than_expected_is_transient():
    fake = FakeDivipola(rows(5))
    fake.total_override = 4
    with pytest.raises(ExtractTransientError):
        run(fake, MemoryRawStore())


def test_empty_dataset_count_zero_is_permanent():
    fake = FakeDivipola([])
    with pytest.raises(ExtractPermanentError, match="positive integer"):
        run(fake, MemoryRawStore())


def test_rows_updated_at_change_during_run_is_transient():
    store = MemoryRawStore()
    fake = FakeDivipola(rows(5))
    fake.bump_after_page_calls = 1
    with pytest.raises(ExtractTransientError, match="rowsUpdatedAt changed"):
        run(fake, store)
    assert store.objects
    assert not any(k.endswith("manifest.json") for k in store.objects)


def test_unchanged_writes_nothing_and_reads_no_page():
    store = MemoryRawStore()
    first = run(FakeDivipola(rows(4)), store)
    before = dict(store.objects)
    fake = FakeDivipola(rows(4))
    second = run(fake, store, batch_id=B2, clock=Clock(NEXT_DAY))
    assert second.outcome == "unchanged"
    assert second.manifest == first.manifest and second.manifest_key == first.manifest_key
    assert store.objects == before
    assert fake.page_params() == []


def test_changed_rows_updated_at_creates_new_batch():
    store = MemoryRawStore()
    run(FakeDivipola(rows(4)), store)
    result = run(
        FakeDivipola(rows(4), updated_at=ROWS_UPDATED_AT + 86400 * 30),
        store,
        batch_id=B2,
        clock=Clock(NEXT_DAY),
    )
    assert result.outcome == "committed" and result.manifest.batch_id == B2
    assert result.rows_updated == "2025-02-23"
    latest = find_latest_committed(store, SOURCE_SYSTEM, DATASET_ID)
    assert latest is not None and latest.batch_id == B2


def test_force_creates_batch_even_if_unchanged():
    store = MemoryRawStore()
    run(FakeDivipola(rows(4)), store)
    result = run(FakeDivipola(rows(4)), store, force=True, batch_id=B2, clock=Clock(NEXT_DAY))
    assert result.outcome == "committed" and result.manifest.batch_id == B2


def test_page_over_8_mib_is_permanent():
    store = MemoryRawStore()
    big = [raw_row(i, nom_mpio="X" * (3 * 1024 * 1024)) for i in range(3)]
    with pytest.raises(ExtractPermanentError, match="byte limit"):
        run(FakeDivipola(big), store, page_size=3)
    assert store.objects == {}


def test_naive_clock_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        extract_divipola(
            FakeDivipola(rows(1)).client(),
            MemoryRawStore(),
            force=False,
            now=lambda: datetime(2026, 10, 13, 12),
            new_batch_id=lambda: B1,
            extractor_version="t",
        )


def bad_rows():
    base = raw_row(0)
    return {
        "missing_key": {k: v for k, v in base.items() if k != "latitud"},
        "extra_key": {**base, "extra": "1"},
        "non_string": {**base, "cod_mpio": 5001},
        "null_value": {**base, "dpto": None},
        "dpto_code_short": raw_row(0, cod_dpto="5", cod_mpio="05001"),
        "mpio_code_short": raw_row(0, cod_mpio="5001"),
        "mpio_code_letters": raw_row(0, cod_mpio="05A01"),
        "prefix_mismatch": raw_row(0, cod_mpio="08001"),
        "unknown_type": raw_row(0, tipo_municipio="Corregimiento"),
        "dot_decimal": raw_row(0, latitud="6.246631"),
        "empty_coordinate": raw_row(0, longitud=""),
        "coordinate_text": raw_row(0, longitud="abc"),
        "blank_name": raw_row(0, nom_mpio=""),
        "padded_name": raw_row(0, nom_mpio=" MEDELLIN"),
        "control_nul": raw_row(0, nom_mpio="ME\x00DELLIN"),
        "control_c1": raw_row(0, dpto="ANTI\x85OQUIA"),
    }


@pytest.mark.parametrize("name", sorted(bad_rows()))
def test_invalid_row_is_permanent_and_writes_nothing(name):
    store = MemoryRawStore()
    data = [raw_row(1), raw_row(2), bad_rows()[name]]
    with pytest.raises(ExtractPermanentError, match="row 2"):
        run(FakeDivipola(data), store, page_size=10)
    assert store.objects == {}


def test_all_known_municipality_types_are_valid():
    data = [
        raw_row(0),
        raw_row(1, tipo_municipio="Isla"),
        raw_row(2, tipo_municipio="Área no municipalizada"),
    ]
    assert run(FakeDivipola(data), MemoryRawStore()).manifest.row_count == 3

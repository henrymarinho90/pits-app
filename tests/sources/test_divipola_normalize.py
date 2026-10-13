"""Offline tests for the DIVIPOLA parser, CSV serializer, manifest and normalizer (D123)."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, date, datetime

import pytest
from divipola_support import B1, B2, ROWS_UPDATED_AT, ROWS_UPDATED_DATE, put_divipola_batch, raw_row

from pits.ingestion.manifest import sha256_hex
from pits.ingestion.raw_store import MemoryRawStore, RawStoreTransientError
from pits.normalized.commit import NormalizedOutcome
from pits.normalized.divipola_csv import HEADER, DivipolaCsvError, serialize_divipola
from pits.normalized.divipola_manifest import (
    DivipolaManifest,
    DivipolaManifestError,
    artifact_prefix,
)
from pits.sources.divipola.normalize import (
    NormalizePermanentError,
    NormalizeTransientError,
    normalize_divipola,
)
from pits.sources.divipola.parse import DivipolaDataError, parse_page, sort_and_check_unique

DAY = date(2026, 10, 13)
BUCKET = "pits-raw"


def sample() -> list[dict[str, str]]:
    return [
        raw_row(0, cod_mpio="05001", nom_mpio="MEDELLÍN"),
        raw_row(
            1,
            cod_dpto="11",
            dpto="BOGOTÁ, D.C.",
            cod_mpio="11001",
            nom_mpio="BOGOTÁ, D.C.",
            longitud="-74,106992",
            latitud="4,649251",
        ),
        raw_row(2, cod_mpio="05002", nom_mpio="ABEJORRAL"),
    ]


def normalize(raw, norm, **kw):
    return normalize_divipola(raw, norm, raw_bucket=BUCKET, **kw)


def read_csv(norm: MemoryRawStore, manifest_key: str) -> list[list[str]]:
    manifest = DivipolaManifest.from_json(norm.get(manifest_key))
    return list(csv.reader(io.StringIO(norm.get(manifest.output.key).decode("utf-8"))))


def test_parse_page_builds_records_in_csv_order():
    (record,) = parse_page([raw_row(0)], page_key="k", page_index=4)
    assert record == (
        "05",
        "ANTIOQUIA",
        "05001",
        "MUNICIPIO 0",
        "Municipio",
        "-75,581775",
        "6,246631",
        4,
        0,
    )


def test_parse_page_error_names_the_row_and_not_the_data():
    with pytest.raises(DivipolaDataError) as exc:
        parse_page(
            [raw_row(0), raw_row(1, cod_mpio="08001")], page_key="payload-00000.json", page_index=0
        )
    assert str(exc.value) == "payload-00000.json#row=1.cod_mpio does not start with cod_dpto"


def test_duplicate_cod_mpio_is_an_error():
    records = parse_page([raw_row(0), raw_row(1, cod_mpio="05001")], page_key="k", page_index=0)
    with pytest.raises(DivipolaDataError, match="duplicate cod_mpio"):
        sort_and_check_unique(records, ["k"])


def test_duplicate_name_inside_a_department_is_an_error():
    records = parse_page(
        [raw_row(0), raw_row(1, nom_mpio="MUNICIPIO 0")], page_key="k", page_index=0
    )
    with pytest.raises(DivipolaDataError, match=r"duplicate \(cod_dpto, nom_mpio\)"):
        sort_and_check_unique(records, ["k"])


def test_same_name_in_two_departments_is_valid():
    records = parse_page(
        [
            raw_row(0, nom_mpio="LA UNION"),
            raw_row(1, cod_dpto="52", dpto="NARIÑO", cod_mpio="52001", nom_mpio="LA UNION"),
        ],
        page_key="k",
        page_index=0,
    )
    sort_and_check_unique(records, ["k"])


def test_two_names_for_one_department_code_is_an_error():
    records = parse_page(
        [raw_row(0), raw_row(1, dpto="ANTIOQUIA NORTE")], page_key="k", page_index=0
    )
    with pytest.raises(DivipolaDataError, match="more than one name"):
        sort_and_check_unique(records, ["k"])


def test_serializer_is_deterministic_quoted_and_sorted():
    records = parse_page(sample(), page_key="k", page_index=0)
    sort_and_check_unique(records, ["k"])
    body = serialize_divipola(records, ["k"])
    assert body == serialize_divipola(records, ["k"])
    text = body.decode("utf-8")
    assert text.startswith(HEADER + "\n") and "\r" not in text and not text.startswith("﻿")
    rows = list(csv.reader(io.StringIO(text)))
    assert [r[2] for r in rows[1:]] == ["05001", "05002", "11001"]
    assert rows[3] == [
        "11",
        "BOGOTÁ, D.C.",
        "11001",
        "BOGOTÁ, D.C.",
        "Municipio",
        "-74,106992",
        "4,649251",
        "k#row=1",
    ]
    assert '"BOGOTÁ, D.C."' in text and '"-74,106992"' in text


def test_serializer_rejects_no_rows():
    with pytest.raises(DivipolaCsvError):
        serialize_divipola([], [])


def test_normalize_creates_artifact_then_already_present():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_divipola_batch(raw, B1, DAY, sample())
    first = normalize(raw, norm)
    assert first.outcome is NormalizedOutcome.CREATED
    assert first.rows_updated == ROWS_UPDATED_DATE and first.rows == 3 and first.batch_id == B1
    prefix = artifact_prefix(ROWS_UPDATED_DATE, first.fingerprint)
    assert first.manifest_key == prefix + "manifest.json"
    assert sorted(norm.objects) == [prefix + "manifest.json", prefix + "municipality.csv"]
    assert list(norm.objects)[-1] == first.manifest_key  # commit marker last
    manifest = DivipolaManifest.from_json(norm.get(first.manifest_key))
    body = norm.get(manifest.output.key)
    assert manifest.output.sha256 == sha256_hex(body) and manifest.output.size_bytes == len(body)
    assert manifest.row_count == 3 and manifest.rows_updated == ROWS_UPDATED_DATE
    before = dict(norm.objects)
    second = normalize(raw, norm)
    assert second.outcome is NormalizedOutcome.ALREADY_PRESENT
    assert second.fingerprint == first.fingerprint and norm.objects == before


def test_already_present_reads_no_payload():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    batch = put_divipola_batch(raw, B1, DAY, sample())
    normalize(raw, norm)
    for entry in batch.files:
        del raw.objects[entry.key]  # payloads gone: only the raw manifest is needed
    assert normalize(raw, norm).outcome is NormalizedOutcome.ALREADY_PRESENT


def test_latest_batch_wins_and_old_artifact_is_untouched():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_divipola_batch(raw, B1, DAY, sample())
    first = normalize(raw, norm)
    put_divipola_batch(
        raw,
        B2,
        date(2026, 10, 20),
        sample()[:2],
        updated_at=ROWS_UPDATED_AT + 86400 * 10,
    )
    before = dict(norm.objects)
    second = normalize(raw, norm)
    assert second.outcome is NormalizedOutcome.CREATED and second.batch_id == B2
    assert second.rows_updated == date(2025, 2, 3) and second.rows == 2
    assert second.fingerprint != first.fingerprint
    assert all(norm.objects[k] == v for k, v in before.items())


def test_rules_version_changes_the_fingerprint():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_divipola_batch(raw, B1, DAY, sample())
    a = normalize(raw, norm)
    b = normalize(raw, norm, rules_version="divipola-v2")
    assert a.fingerprint != b.fingerprint and b.outcome is NormalizedOutcome.CREATED


def test_without_raw_batches_is_permanent():
    with pytest.raises(NormalizePermanentError, match="No committed raw DIVIPOLA batch"):
        normalize(MemoryRawStore(), MemoryRawStore())


def test_invalid_payload_row_is_permanent_and_writes_nothing():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_divipola_batch(raw, B1, DAY, [*sample(), raw_row(9, tipo_municipio="X")])
    with pytest.raises(NormalizePermanentError, match="tipo_municipio"):
        normalize(raw, norm)
    assert norm.objects == {}


def test_corrupt_payload_is_permanent():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    batch = put_divipola_batch(raw, B1, DAY, sample())
    raw.objects[batch.files[0].key] = b"[]"
    with pytest.raises(NormalizePermanentError):
        normalize(raw, norm)


def test_transient_store_failure_is_transient():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_divipola_batch(raw, B1, DAY, sample())

    def boom(prefix):
        raise RawStoreTransientError("simulated")

    raw.list_prefixes = boom
    with pytest.raises(NormalizeTransientError):
        normalize(raw, norm)


def test_manifest_roundtrip_and_strictness():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_divipola_batch(raw, B1, DAY, sample())
    result = normalize(raw, norm)
    data = norm.get(result.manifest_key)
    manifest = DivipolaManifest.from_json(data)
    assert manifest.to_json() == data
    parsed = json.loads(data)
    parsed["row_count"] = 0
    with pytest.raises(DivipolaManifestError):
        DivipolaManifest.from_json(json.dumps(parsed).encode())
    parsed = json.loads(data)
    parsed["extra"] = 1
    with pytest.raises(DivipolaManifestError):
        DivipolaManifest.from_json(json.dumps(parsed).encode())
    parsed = json.loads(data)
    parsed["input_fingerprint"] = "0" * 64
    with pytest.raises(DivipolaManifestError, match="fingerprint"):
        DivipolaManifest.from_json(json.dumps(parsed).encode())
    parsed = json.loads(data)
    parsed["output"]["key"] = "elsewhere/municipality.csv"
    with pytest.raises(DivipolaManifestError, match="output.key"):
        DivipolaManifest.from_json(json.dumps(parsed).encode())
    assert datetime(2025, 1, 24, tzinfo=UTC).date() == manifest.rows_updated

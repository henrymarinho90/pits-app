"""Offline tests for the regional brand fleet CSV, manifest and normalizer (D137)."""

from __future__ import annotations

import csv
import io
import json
from datetime import date

import pytest
from brand_fleet_support import (
    B1,
    B2,
    BOYACA,
    RISARALDA,
    ROWS_UPDATED_AT,
    ROWS_UPDATED_DATE,
    boyaca_row,
    put_brand_batch,
    risaralda_row,
)

from pits.ingestion.manifest import Manifest, manifest_key, sha256_hex
from pits.ingestion.raw_store import MemoryRawStore, RawStoreTransientError, batch_prefix
from pits.normalized.brand_fleet_csv import HEADER, BrandFleetCsvError, serialize_brand_count
from pits.normalized.brand_fleet_manifest import (
    BrandFleetManifest,
    BrandFleetManifestError,
    artifact_prefix,
)
from pits.normalized.commit import NormalizedOutcome
from pits.sources.brand_fleet.normalize import (
    NormalizePermanentError,
    NormalizeTransientError,
    normalize_brand_fleet,
)

DAY = date(2026, 10, 14)
BUCKET = "pits-raw"
PLATE = "ZZZ999"


def boyaca_sample() -> list[dict[str, str]]:
    return [
        boyaca_row(0, clase="AUTOMOVIL", marca="MARCA X", linea="L1"),
        boyaca_row(1, clase="AUTOMOVIL", marca="MARCA X", linea="L1"),
        boyaca_row(2, clase="AUTOMOVIL", marca="MARCA X", linea="L1", servicio="PUBLICO"),
        boyaca_row(3, clase="MOTOCICLETA", marca="MARCA, Y", linea="L2", estado="CANCELADO"),
        boyaca_row(4, clase="AUTOMOVIL", marca="MARCA X", linea="L1"),
    ]


def risaralda_sample() -> list[dict[str, str]]:
    return [
        risaralda_row(0, clase="MOTOCICLETA", marca="VICTORY", linea="ONE"),
        risaralda_row(1, clase="MOTOCICLETA", marca="VICTORY", linea="ONE"),
        risaralda_row(2, clase="AUTOMOVIL", marca="MARCA Z", linea="Z1"),
    ]


def normalize(raw, norm, source=BOYACA, **kw):
    return normalize_brand_fleet(raw, norm, source, raw_bucket=BUCKET, **kw)


def read_rows(norm: MemoryRawStore, manifest_key_: str) -> list[list[str]]:
    manifest = BrandFleetManifest.from_json(norm.get(manifest_key_))
    return list(csv.reader(io.StringIO(norm.get(manifest.output.key).decode("utf-8"))))


def test_serializer_is_deterministic_quoted_and_checks_order():
    rows = [("A", "B, C", "D", "", "", 2), ("A", "B, C", "E", "", "", 1)]
    body = serialize_brand_count(rows, "k")
    assert body == serialize_brand_count(rows, "k")
    text = body.decode("utf-8")
    assert text.startswith(HEADER + "\n") and "\r" not in text and not text.startswith("﻿")
    assert text.splitlines()[1] == 'A,"B, C",D,,,2,k'
    with pytest.raises(BrandFleetCsvError, match="sorted and unique"):
        serialize_brand_count(list(reversed(rows)), "k")
    with pytest.raises(BrandFleetCsvError, match="sorted and unique"):
        serialize_brand_count([rows[0], rows[0]], "k")
    with pytest.raises(BrandFleetCsvError, match="positive"):
        serialize_brand_count([("A", "B", "C", "", "", 0)], "k")
    with pytest.raises(BrandFleetCsvError, match="no rows"):
        serialize_brand_count([], "k")


def test_boyaca_aggregates_by_five_keys_and_conserves_vehicles():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    batch = put_brand_batch(raw, BOYACA, B1, DAY, boyaca_sample())
    result = normalize(raw, norm)
    assert result.outcome is NormalizedOutcome.CREATED
    assert (result.rows, result.vehicles, result.batch_id) == (3, 5, B1)
    assert result.rows_updated == ROWS_UPDATED_DATE
    ref = manifest_key(batch_prefix(BOYACA.source_system, DAY, B1))
    assert read_rows(norm, result.manifest_key) == [
        HEADER.split(","),
        ["AUTOMOVIL", "MARCA X", "L1", "PARTICULAR", "ACTIVO", "3", ref],
        ["AUTOMOVIL", "MARCA X", "L1", "PUBLICO", "ACTIVO", "1", ref],
        ["MOTOCICLETA", "MARCA, Y", "L2", "PARTICULAR", "CANCELADO", "1", ref],
    ]
    assert result.vehicles == batch.row_count


def test_risaralda_has_empty_service_and_status_and_no_plate_anywhere():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_brand_batch(raw, RISARALDA, B1, DAY, risaralda_sample())
    result = normalize(raw, norm, RISARALDA)
    assert (result.rows, result.vehicles) == (2, 3)
    rows = read_rows(norm, result.manifest_key)
    assert rows[1][:6] == ["AUTOMOVIL", "MARCA Z", "Z1", "", "", "1"]
    assert rows[2][:6] == ["MOTOCICLETA", "VICTORY", "ONE", "", "", "2"]
    assert "placa" not in rows[0]
    for body in norm.objects.values():
        assert b"placa" not in body.lower()


def test_plate_in_a_raw_payload_is_permanent_and_writes_nothing():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    data = risaralda_sample()
    data[1] = {**data[1], "placa": PLATE}  # a legacy batch stored by a faulty extractor
    put_brand_batch(raw, RISARALDA, B1, DAY, data)
    with pytest.raises(NormalizePermanentError, match=r"#row=1\.placa") as info:
        normalize(raw, norm, RISARALDA)
    assert PLATE not in str(info.value)
    assert norm.objects == {}


def test_normalize_is_byte_deterministic_across_stores():
    bodies = []
    for _ in range(2):
        raw, norm = MemoryRawStore(), MemoryRawStore()
        put_brand_batch(raw, BOYACA, B1, DAY, boyaca_sample())
        normalize(raw, norm)
        bodies.append(dict(norm.objects))
    assert bodies[0] == bodies[1]
    assert {sha256_hex(b) for b in bodies[0].values()} == {
        sha256_hex(b) for b in bodies[1].values()
    }


def test_row_order_inside_the_raw_batch_does_not_change_the_csv_body():
    a, b = MemoryRawStore(), MemoryRawStore()
    na, nb = MemoryRawStore(), MemoryRawStore()
    put_brand_batch(a, BOYACA, B1, DAY, boyaca_sample())
    put_brand_batch(b, BOYACA, B1, DAY, list(reversed(boyaca_sample())))
    ra, rb = normalize(a, na), normalize(b, nb)
    csv_a = [v for k, v in na.objects.items() if k.endswith(".csv")]
    csv_b = [v for k, v in nb.objects.items() if k.endswith(".csv")]
    assert csv_a == csv_b and ra.rows == rb.rows


def test_creates_artifact_then_already_present_without_reading_payloads():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    batch = put_brand_batch(raw, BOYACA, B1, DAY, boyaca_sample())
    first = normalize(raw, norm)
    prefix = artifact_prefix(BOYACA.source_system, ROWS_UPDATED_DATE, first.fingerprint)
    assert first.manifest_key == prefix + "manifest.json"
    assert sorted(norm.objects) == [prefix + "brand_count.csv", prefix + "manifest.json"]
    assert list(norm.objects)[-1] == first.manifest_key  # commit marker last
    manifest = BrandFleetManifest.from_json(norm.get(first.manifest_key))
    body = norm.get(manifest.output.key)
    assert manifest.output.sha256 == sha256_hex(body) and manifest.output.size_bytes == len(body)
    assert (manifest.row_count, manifest.vehicle_total) == (3, 5)
    before = dict(norm.objects)
    for entry in batch.files:
        del raw.objects[entry.key]  # payloads gone: only the raw manifest is needed
    second = normalize(raw, norm)
    assert second.outcome is NormalizedOutcome.ALREADY_PRESENT
    assert second.fingerprint == first.fingerprint and norm.objects == before
    assert (second.rows, second.vehicles) == (3, 5)


def test_latest_batch_wins_and_old_artifact_is_untouched():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_brand_batch(raw, BOYACA, B1, DAY, boyaca_sample())
    first = normalize(raw, norm)
    put_brand_batch(
        raw,
        BOYACA,
        B2,
        date(2026, 10, 20),
        boyaca_sample()[:2],
        updated_at=ROWS_UPDATED_AT + 86400 * 10,
    )
    before = dict(norm.objects)
    second = normalize(raw, norm)
    assert second.outcome is NormalizedOutcome.CREATED and second.batch_id == B2
    assert second.fingerprint != first.fingerprint and second.vehicles == 2
    assert all(norm.objects[k] == v for k, v in before.items())


def test_sources_are_independent():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_brand_batch(raw, BOYACA, B1, DAY, boyaca_sample())
    with pytest.raises(NormalizePermanentError, match="No committed raw batch"):
        normalize(raw, norm, RISARALDA)


def test_rules_version_changes_the_fingerprint():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_brand_batch(raw, BOYACA, B1, DAY, boyaca_sample())
    a = normalize(raw, norm)
    b = normalize(raw, norm, rules_version="brand-fleet-v2")
    assert a.fingerprint != b.fingerprint and b.outcome is NormalizedOutcome.CREATED


def test_without_raw_batches_is_permanent():
    with pytest.raises(NormalizePermanentError, match="No committed raw batch"):
        normalize(MemoryRawStore(), MemoryRawStore())


def test_raw_batch_with_other_schema_is_permanent():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_brand_batch(raw, RISARALDA, B1, DAY, risaralda_sample())
    manifest = Manifest.from_json(
        raw.get(manifest_key(batch_prefix(RISARALDA.source_system, DAY, B1)))
    )
    # the same batch re-declared with the full source schema (including the plate column)
    data = json.loads(manifest.to_json())
    data["schema"] = [{"name": c.name, "data_type": c.data_type} for c in RISARALDA.source_schema]
    key = manifest_key(batch_prefix(RISARALDA.source_system, DAY, B1))
    raw.objects[key] = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()
    with pytest.raises(NormalizePermanentError, match="schema other than the requested"):
        normalize(raw, norm, RISARALDA)
    assert norm.objects == {}


def test_conservation_failure_is_permanent_and_writes_nothing(monkeypatch):
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_brand_batch(raw, BOYACA, B1, DAY, boyaca_sample())
    import pits.sources.brand_fleet.normalize as module

    real = module._aggregate
    monkeypatch.setattr(module, "_aggregate", lambda *a: real(*a)[:-1])  # lose a row group
    with pytest.raises(NormalizePermanentError, match="Conservation failed"):
        normalize(raw, norm)
    assert norm.objects == {}


def test_invalid_payload_row_is_permanent_and_writes_nothing():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_brand_batch(raw, BOYACA, B1, DAY, [*boyaca_sample(), boyaca_row(9, marca="")])
    with pytest.raises(NormalizePermanentError, match="marca"):
        normalize(raw, norm)
    assert norm.objects == {}


def test_corrupt_payload_is_permanent():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    batch = put_brand_batch(raw, BOYACA, B1, DAY, boyaca_sample())
    raw.objects[batch.files[0].key] = b"[]"
    with pytest.raises(NormalizePermanentError):
        normalize(raw, norm)


def test_transient_store_failure_is_transient():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_brand_batch(raw, BOYACA, B1, DAY, boyaca_sample())

    def boom(prefix):
        raise RawStoreTransientError("simulated")

    raw.list_prefixes = boom
    with pytest.raises(NormalizeTransientError):
        normalize(raw, norm)


def test_manifest_roundtrip_and_strictness():
    raw, norm = MemoryRawStore(), MemoryRawStore()
    put_brand_batch(raw, BOYACA, B1, DAY, boyaca_sample())
    data = norm_manifest_bytes(raw, norm)
    manifest = BrandFleetManifest.from_json(data)
    assert manifest.to_json() == data

    def mutated(**changes):
        parsed = json.loads(data)
        for path, value in changes.items():
            target = parsed
            *parents, leaf = path.split("__")
            for p in parents:
                target = target[p]
            target[leaf] = value
        return json.dumps(parsed).encode()

    with pytest.raises(BrandFleetManifestError):
        BrandFleetManifest.from_json(mutated(row_count=0))
    with pytest.raises(BrandFleetManifestError):
        BrandFleetManifest.from_json(mutated(extra=1))
    with pytest.raises(BrandFleetManifestError, match="fingerprint"):
        BrandFleetManifest.from_json(mutated(input_fingerprint="0" * 64))
    with pytest.raises(BrandFleetManifestError, match="output.key"):
        BrandFleetManifest.from_json(mutated(output__key="elsewhere/brand_count.csv"))
    with pytest.raises(BrandFleetManifestError, match="Unexpected source"):
        BrandFleetManifest.from_json(mutated(dataset_id="u3vn-bdcy"))
    with pytest.raises(BrandFleetManifestError, match="vehicle_total"):
        BrandFleetManifest.from_json(mutated(vehicle_total=1))


def norm_manifest_bytes(raw: MemoryRawStore, norm: MemoryRawStore) -> bytes:
    return norm.get(normalize(raw, norm).manifest_key)

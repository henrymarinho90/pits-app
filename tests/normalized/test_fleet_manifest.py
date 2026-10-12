"""Pure tests for pits.normalized.fleet_manifest (strict, deterministic, self-consistent)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest
from runt_support import B1

from pits.normalized.fingerprint import InputRef, Transform, compute_input_fingerprint
from pits.normalized.fleet_csv import HEADER_BYTES
from pits.normalized.fleet_manifest import (
    FleetManifest,
    FleetManifestError,
    PartEntry,
    Publication,
    artifact_prefix,
)

TRANSFORM = Transform("runt_to_vehicle_fleet_snapshot", "runt-v1")
REF = InputRef(
    B1,
    date(2026, 10, 12),
    datetime(2026, 10, 12, 21, 50, tzinfo=UTC),
    "full",
    "mintransporte_runt_parque/extraction_date=2026-10-12/batch_id=" + B1 + "/manifest.json",
    "a" * 64,
)
FP = compute_input_fingerprint(TRANSFORM, "pits-raw", (REF,))
PREFIX = artifact_prefix("2026-10", FP)
H = len(HEADER_BYTES)


def make(**over) -> FleetManifest:
    fields = {
        "source_system": "mintransporte_runt_parque",
        "dataset_id": "u3vn-bdcy",
        "transform": TRANSFORM,
        "raw_bucket": "pits-raw",
        "inputs": (REF,),
        "input_fingerprint": FP,
        "publication": Publication(2026, 10),
        "row_count": 5,
        "vehicle_count_total": 20,
        "content_sha256": "b" * 64,
        "content_size_bytes": H + 100 + 50,
        "parts": (
            PartEntry(PREFIX + "part-00000.csv", "c" * 64, H + 100, 3),
            PartEntry(PREFIX + "part-00001.csv", "d" * 64, H + 50, 2),
        ),
    }
    return FleetManifest(**{**fields, **over})


def test_key_layout_matches_d98():
    assert PREFIX == (
        "vehicle_fleet_snapshot/source_system=mintransporte_runt_parque/"
        f"publication_month=2026-10/fingerprint={FP}/"
    )
    assert make().manifest_key == PREFIX + "manifest.json"


def test_roundtrip_and_deterministic_bytes():
    manifest = make()
    data = manifest.to_json()
    assert FleetManifest.from_json(data) == manifest
    assert make().to_json() == data and data.endswith(b"}\n") and b"\r" not in data
    top = json.loads(data)
    assert top["dataset"] == "vehicle_fleet_snapshot" and top["manifest_version"] == 1
    assert top["content_sha256"] == "b" * 64 and top["content_size_bytes"] == H + 150
    assert list(top) == sorted(top)  # sorted keys


@pytest.mark.parametrize(
    "over",
    [
        {"input_fingerprint": "e" * 64},
        {"row_count": 6},
        {"content_size_bytes": 1},
        {"dataset_id": "other"},
        {"inputs": ()},
        {"inputs": (REF, REF)},
        {"publication": Publication(2026, 13)},
        {"content_sha256": "xyz"},
        {"vehicle_count_total": -1},
        {"parts": ()},
        {"parts": (PartEntry(PREFIX + "part-00001.csv", "c" * 64, H + 150, 5),)},
        {"parts": (PartEntry(PREFIX + "part-00000.csv", "c" * 64, H + 150, 20_001),)},
        {"parts": (PartEntry(PREFIX + "part-00000.csv", "c" * 64, 9 * 1024 * 1024, 5),)},
    ],
)
def test_inconsistent_manifest_is_rejected(over):
    with pytest.raises(FleetManifestError):
        make(**over)


def test_from_json_is_strict():
    good = json.loads(make().to_json())
    for mutate in (
        lambda d: d.pop("parts"),
        lambda d: d.update(extra=1),
        lambda d: d["parts"][0].update(row_count="3"),
        lambda d: d.update(manifest_version=2),
    ):
        broken = json.loads(json.dumps(good))
        mutate(broken)
        with pytest.raises(FleetManifestError):
            FleetManifest.from_json(json.dumps(broken).encode())
    with pytest.raises(FleetManifestError):
        FleetManifest.from_json(b"not json")
    with pytest.raises(FleetManifestError):
        FleetManifest.from_json(b"\xff")

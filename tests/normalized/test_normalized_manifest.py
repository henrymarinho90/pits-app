"""Pure tests for pits.normalized.manifest."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from pits.ingestion.manifest import sha256_hex
from pits.normalized.manifest import (
    Coverage,
    InputRef,
    NormalizedManifest,
    NormalizedManifestError,
    Output,
    Transform,
    compute_input_fingerprint,
)

TRANSFORM = Transform("trm_to_fx_rate", "trm-v1")
B1 = "0b6f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a10"
B2 = "1c7a7d2f-4d2b-4a1f-8b62-3e5d7a9fab21"


def ref(batch_id, day, mode="full"):
    key = f"superfinanciera_trm/extraction_date={day}/batch_id={batch_id}/manifest.json"
    return InputRef(
        batch_id,
        date.fromisoformat(day),
        datetime(2026, 10, 10, 12, 0, 30, tzinfo=UTC),
        mode,
        key,
        sha256_hex(key.encode()),
    )


INPUTS = (ref(B1, "2026-10-09"), ref(B2, "2026-10-10", "incremental"))


FINGERPRINT = compute_input_fingerprint(TRANSFORM, "pits-raw", INPUTS)
CSV_KEY = (
    "fx_rate/source_system=superfinanciera_trm/inputs_until=2026-10-10/"
    f"fingerprint={FINGERPRINT}/fx_rate.csv"
)


def make(**overrides):
    base = {
        "source_system": "superfinanciera_trm",
        "dataset_id": "32sa-8pi3",
        "transform": TRANSFORM,
        "raw_bucket": "pits-raw",
        "inputs": INPUTS,
        "baseline_batch_id": B1,
        "input_fingerprint": compute_input_fingerprint(TRANSFORM, "pits-raw", INPUTS),
        "coverage": Coverage(date(1991, 12, 2), date(2026, 10, 13)),
        "row_count": 12000,
        "max_range_days": 4,
        "output": Output(CSV_KEY, sha256_hex(b"csv"), 3, "text/csv"),
    }
    base.update(overrides)
    return NormalizedManifest(**base)


def mutated(mutate):
    data = json.loads(make().to_json())
    mutate(data)
    return json.dumps(data).encode()


def test_roundtrip_is_byte_identical():
    m = make()
    data = m.to_json()
    assert NormalizedManifest.from_json(data) == m
    assert NormalizedManifest.from_json(data).to_json() == data


def test_json_format():
    data = make().to_json()
    assert data.endswith(b"\n") and b"\r" not in data
    text = data.decode()
    assert list(json.loads(text)) == sorted(json.loads(text))
    assert '"dataset": "fx_rate"' in text and '"manifest_version": 1' in text
    assert '"finished_at": "2026-10-10T12:00:30.000000Z"' in text
    assert '"from": "1991-12-02"' in text


def test_fingerprint_depends_on_inputs_order_bucket_and_rules_version():
    base = compute_input_fingerprint(TRANSFORM, "pits-raw", INPUTS)
    assert base == compute_input_fingerprint(TRANSFORM, "pits-raw", INPUTS)
    assert base != compute_input_fingerprint(TRANSFORM, "pits-raw", INPUTS[::-1])
    assert base != compute_input_fingerprint(TRANSFORM, "other", INPUTS)
    assert base != compute_input_fingerprint(Transform("trm_to_fx_rate", "v2"), "pits-raw", INPUTS)
    assert base != compute_input_fingerprint(TRANSFORM, "pits-raw", INPUTS[:1])
    assert len(base) == 64


def test_fingerprint_ignores_fields_that_are_not_content_identity():
    other = (replace(INPUTS[0], mode="since"), INPUTS[1])
    assert compute_input_fingerprint(TRANSFORM, "pits-raw", other) == compute_input_fingerprint(
        TRANSFORM, "pits-raw", INPUTS
    )


def test_from_json_rejects_wrong_fingerprint():
    with pytest.raises(NormalizedManifestError, match="fingerprint"):
        NormalizedManifest.from_json(
            mutated(lambda d: d.__setitem__("input_fingerprint", "0" * 64))
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.__setitem__("manifest_version", 2),
        lambda d: d.__setitem__("dataset", "other"),
        lambda d: d.__setitem__("extra", 1),
        lambda d: d.pop("row_count"),
        lambda d: d.__setitem__("row_count", "12"),
        lambda d: d.__setitem__("row_count", True),
        lambda d: d["coverage"].__setitem__("from", "1991-12-02T00:00:00"),
        lambda d: d["output"].pop("sha256"),
        lambda d: d["output"].__setitem__("sha256", "ABC"),
        lambda d: d["inputs"][0].__setitem__("finished_at", "2026-10-10T12:00:30"),
        lambda d: d.__setitem__("inputs", []),
        lambda d: d.__setitem__("baseline_batch_id", "zzz"),
        lambda d: d.__setitem__("max_range_days", -1),
    ],
)
def test_from_json_is_strict(mutate):
    with pytest.raises(NormalizedManifestError):
        NormalizedManifest.from_json(mutated(mutate))


@pytest.mark.parametrize("data", [b"{oops", b"\xff\xfe", b"[]", b'"x"'])
def test_from_json_rejects_garbage(data):
    with pytest.raises(NormalizedManifestError):
        NormalizedManifest.from_json(data)


def test_naive_input_timestamp_rejected_on_construction():
    bad = replace(INPUTS[0], finished_at=datetime(2026, 10, 10, 12))
    with pytest.raises(NormalizedManifestError, match="timezone-aware"):
        make(
            inputs=(bad, INPUTS[1]),
            input_fingerprint=compute_input_fingerprint(TRANSFORM, "pits-raw", (bad, INPUTS[1])),
        )


def test_no_execution_metadata_in_artifact():
    text = make().to_json().decode()
    for forbidden in ("generated_at", "created_at", "uuid", 'version": "0', "run_id"):
        assert forbidden not in text


def test_golden_fingerprint_is_pinned():
    inputs = (
        InputRef(
            B1,
            date(2026, 10, 9),
            datetime(2026, 10, 9, 12, tzinfo=UTC),
            "full",
            "superfinanciera_trm/extraction_date=2026-10-09/batch_id=" + B1 + "/manifest.json",
            "a" * 64,
        ),
    )
    # Any change here silently invalidates every existing normalized artifact (D76).
    assert compute_input_fingerprint(Transform("trm_to_fx_rate", "trm-v1"), "pits-raw", inputs) == (
        "2b07ad36c3f4458aed6e7e2eca9df6f3c00b7fb76f9f858085c472cd588d1b15"
    )


def test_semantic_validation_on_construction():
    bad_input = replace(INPUTS[0], mode="weekly")
    for kwargs, match in [
        ({"source_system": "other"}, "Unexpected source"),
        ({"dataset_id": "zzzz-0000"}, "Unexpected source"),
        ({"baseline_batch_id": "NOT-A-UUID"}, "baseline_batch_id"),
        (
            {"output": Output("fx_rate/x/fx_rate.csv", sha256_hex(b"c"), 1, "text/csv")},
            "output.key",
        ),
        (
            {"output": Output(CSV_KEY.replace("fx_rate/", "raw/", 1), sha256_hex(b"c"), 1, "t")},
            "output.key",
        ),
    ]:
        with pytest.raises(NormalizedManifestError, match=match):
            make(**kwargs)
    for bad, match in [
        (bad_input, "Invalid input mode"),
        (replace(INPUTS[0], batch_id="0B6F6C1E-3C1A-4F0E-9A51-2D4C6F8E9A10"), "batch_id"),
        (replace(INPUTS[0], batch_id="nope"), "batch_id"),
    ]:
        inputs = (bad, INPUTS[1])
        fp = compute_input_fingerprint(TRANSFORM, "pits-raw", inputs)
        out = Output(CSV_KEY.replace(FINGERPRINT, fp), sha256_hex(b"c"), 1, "text/csv")
        with pytest.raises(NormalizedManifestError, match=match):
            make(inputs=inputs, input_fingerprint=fp, output=out)

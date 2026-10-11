"""Offline tests for pits.normalized.reader (MemoryRawStore + the real normalizer)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest
from trm_helpers import B1, B2, B3, put_raw_batch, raw_row

from pits.ingestion.manifest import sha256_hex
from pits.ingestion.raw_store import MemoryRawStore, RawStoreError, RawStoreTransientError
from pits.normalized.manifest import (
    Coverage,
    NormalizedManifest,
    Output,
    compute_input_fingerprint,
)
from pits.normalized.reader import (
    NormalizedReadPermanentError,
    NormalizedReadTransientError,
    load_artifact,
    read_artifact,
    select_artifact,
)
from pits.sources.trm.contract import BACKFILL_FROM
from pits.sources.trm.normalize import normalize_trm

RAW_BUCKET = "pits-raw"
DAY1 = date(2026, 10, 9)
DAY2 = date(2026, 10, 10)


def _full_rows():
    return [
        raw_row(BACKFILL_FROM, date(2026, 10, 9), "3000.5"),
        raw_row(date(2026, 10, 10), date(2026, 10, 13), "3194.44"),
    ]


class Env:
    """A raw store with a full batch (+ optional incremental) and the normalized store."""

    def __init__(self):
        self.raw = MemoryRawStore()
        self.norm = MemoryRawStore()
        put_raw_batch(self.raw, B1, DAY1, "full", _full_rows())

    def normalize(self):
        return normalize_trm(self.raw, self.norm, raw_bucket=RAW_BUCKET)

    def add_incremental(self, batch_id=B2, day=DAY2, valor="3200"):
        put_raw_batch(
            self.raw,
            batch_id,
            day,
            "incremental",
            [raw_row(date(2026, 10, 14), date(2026, 10, 14), valor)],
            from_exclusive=date(2026, 10, 10),
        )


@pytest.fixture
def two_artifacts():
    env = Env()
    old = env.normalize()
    env.add_incremental()
    new = env.normalize()
    assert old.fingerprint != new.fingerprint
    return env, old, new


def parsed(env, result):
    return NormalizedManifest.from_json(env.norm.get(result.manifest_key))


def clone(env, base_result, csv_bytes=None, **changes):
    """Write a synthetic, internally consistent artifact derived from a real one."""
    base = parsed(env, base_result)
    csv = csv_bytes if csv_bytes is not None else env.norm.get(base_result.csv_key)
    transform = changes.get("transform", base.transform)
    bucket = changes.get("raw_bucket", base.raw_bucket)
    inputs = changes.get("inputs", base.inputs)
    fingerprint = compute_input_fingerprint(transform, bucket, inputs)
    until = max(i.extraction_date for i in inputs).isoformat()
    directory = (
        f"fx_rate/source_system=superfinanciera_trm/inputs_until={until}/fingerprint={fingerprint}/"
    )
    output = Output(directory + "fx_rate.csv", sha256_hex(csv), len(csv), "text/csv")
    m = replace(base, **{**changes, "input_fingerprint": fingerprint, "output": output})
    env.norm.objects[m.output.key] = csv  # overwrite: tamper tests reuse the real directory
    env.norm.objects[directory + "manifest.json"] = m.to_json()
    return directory, m


def test_selects_the_artifact_with_the_latest_last_input(two_artifacts):
    env, old, new = two_artifacts
    selected = select_artifact(env.norm, RAW_BUCKET)
    assert selected.manifest.input_fingerprint == new.fingerprint
    assert selected.manifest_key == new.manifest_key and selected.csv_key == new.csv_key


def test_selection_does_not_depend_on_listing_order(two_artifacts):
    env, _, new = two_artifacts

    class Reversed(MemoryRawStore):
        def list_prefixes(self, prefix):
            return sorted(super().list_prefixes(prefix), reverse=True)

    store = Reversed()
    store.objects = env.norm.objects
    assert select_artifact(store, RAW_BUCKET).manifest.input_fingerprint == new.fingerprint


def test_commit_order_uses_finished_at_before_batch_id():
    # Same extraction_date; B3 sorts after B2 by batch_id but finished earlier -> B2 is later.
    env = Env()
    base = env.normalize()
    ref = parsed(env, base).inputs[0]
    early = replace(ref, batch_id=B3, finished_at=datetime(2026, 10, 9, 13, tzinfo=UTC))
    late = replace(ref, batch_id=B2, finished_at=datetime(2026, 10, 9, 23, tzinfo=UTC))
    clone(env, base, inputs=(early,), baseline_batch_id=B3)
    _, winner = clone(env, base, inputs=(late,), baseline_batch_id=B2)
    selected = select_artifact(env.norm, RAW_BUCKET)
    assert selected.manifest.input_fingerprint == winner.input_fingerprint
    assert selected.commit_order == (DAY1, late.finished_at, B2)


def test_returns_load_run_metadata(two_artifacts):
    env, _, new = two_artifacts
    art = load_artifact(env.norm, RAW_BUCKET)
    m = parsed(env, new)
    assert art.csv_bytes == env.norm.get(new.csv_key)
    assert art.fingerprint == new.fingerprint
    assert (art.transform_name, art.rules_version) == ("trm_to_fx_rate", "trm-v1")
    assert (art.coverage_from, art.coverage_to) == (BACKFILL_FROM, date(2026, 10, 14))
    assert art.row_count == new.rows
    assert art.manifest_sha256 == sha256_hex(env.norm.get(new.manifest_key))
    assert art.csv_sha256 == m.output.sha256 and art.csv_size_bytes == len(art.csv_bytes)
    assert art.last_input_batch_id == B2 and art.last_input_extraction_date == DAY2
    assert art.last_input_finished_at == m.inputs[-1].finished_at
    assert art.manifest_key == new.manifest_key and art.csv_key == new.csv_key


def test_orphan_csv_is_ignored(two_artifacts):
    env, old, new = two_artifacts
    del env.norm.objects[new.manifest_key]  # CSV stays, manifest (commit marker) missing
    assert select_artifact(env.norm, RAW_BUCKET).manifest.input_fingerprint == old.fingerprint


def test_only_orphans_means_no_artifact():
    env = Env()
    result = env.normalize()
    del env.norm.objects[result.manifest_key]
    with pytest.raises(NormalizedReadPermanentError, match="No committed"):
        select_artifact(env.norm, RAW_BUCKET)


def test_empty_store_has_no_artifact():
    with pytest.raises(NormalizedReadPermanentError, match="No committed"):
        select_artifact(MemoryRawStore(), RAW_BUCKET)


@pytest.mark.parametrize("data", [b"not json", b"{}", b'{"manifest_version": 2}', b"\xff\xfe"])
def test_corrupt_manifest_is_permanent_even_if_not_the_latest(two_artifacts, data):
    env, old, _ = two_artifacts
    env.norm.objects[old.manifest_key] = data
    with pytest.raises(NormalizedReadPermanentError, match="manifest.json"):
        select_artifact(env.norm, RAW_BUCKET)


def test_manifest_of_another_version_is_permanent():
    env = Env()
    result = env.normalize()
    text = (
        env.norm.get(result.manifest_key)
        .decode()
        .replace('"manifest_version": 1', '"manifest_version": 2')
    )
    env.norm.objects[result.manifest_key] = text.encode()
    with pytest.raises(NormalizedReadPermanentError, match="manifest_version"):
        select_artifact(env.norm, RAW_BUCKET)


def test_manifest_under_the_wrong_fingerprint_key_is_permanent(two_artifacts):
    env, old, new = two_artifacts
    env.norm.objects[old.manifest_key] = env.norm.get(new.manifest_key)  # swapped content
    with pytest.raises(NormalizedReadPermanentError, match="does not match its key"):
        select_artifact(env.norm, RAW_BUCKET)


def test_manifest_under_the_wrong_inputs_until_is_permanent():
    env = Env()
    result = env.normalize()
    moved = result.manifest_key.replace("inputs_until=2026-10-09", "inputs_until=2026-10-01")
    env.norm.objects[moved] = env.norm.objects.pop(result.manifest_key)
    env.norm.objects[moved.replace("manifest.json", "fx_rate.csv")] = env.norm.get(result.csv_key)
    with pytest.raises(NormalizedReadPermanentError, match="inputs_until"):
        select_artifact(env.norm, RAW_BUCKET)


def test_output_key_pointing_elsewhere_is_permanent():
    env = Env()
    result = env.normalize()
    base = parsed(env, result)
    wrong = result.csv_key.replace("fx_rate.csv", "other.csv")
    bad = replace(base, output=replace(base.output, key=wrong))
    env.norm.objects[result.manifest_key] = bad.to_json()
    with pytest.raises(NormalizedReadPermanentError, match="output.key"):
        select_artifact(env.norm, RAW_BUCKET)


def test_other_rules_version_is_not_eligible():
    env = Env()
    result = env.normalize()
    clone(env, result, transform=replace(parsed(env, result).transform, rules_version="trm-v2"))
    # the real trm-v1 artifact is still the one chosen
    assert select_artifact(env.norm, RAW_BUCKET).manifest.input_fingerprint == result.fingerprint


@pytest.mark.parametrize("change", ["rules_version", "raw_bucket"])
def test_only_other_rules_version_or_bucket_means_no_artifact(change):
    env = Env()
    result = env.normalize()
    base = parsed(env, result)
    if change == "rules_version":
        clone(env, result, transform=replace(base.transform, rules_version="trm-v2"))
    else:
        clone(env, result, raw_bucket="other-bucket")
    del env.norm.objects[result.manifest_key]
    del env.norm.objects[result.csv_key]
    with pytest.raises(NormalizedReadPermanentError, match="No committed"):
        select_artifact(env.norm, RAW_BUCKET)


def test_forced_fingerprint_with_other_bucket_or_rules_is_rejected():
    env = Env()
    result = env.normalize()
    base = parsed(env, result)
    for change in (
        {"raw_bucket": "other-bucket"},
        {"transform": replace(base.transform, rules_version="trm-v2")},
    ):
        _, m = clone(env, result, **change)
        with pytest.raises(NormalizedReadPermanentError, match="differs"):
            select_artifact(env.norm, RAW_BUCKET, fingerprint=m.input_fingerprint)


def test_tie_with_different_fingerprints_is_ambiguous():
    env = Env()
    result = env.normalize()
    base = parsed(env, result)
    last = base.inputs[-1]
    other = replace(last, batch_id=B3, finished_at=datetime(2026, 10, 9, 1, tzinfo=UTC))
    # Same last input as the real artifact but a different earlier input -> other fingerprint.
    clone(env, result, inputs=(other, last), baseline_batch_id=last.batch_id)
    with pytest.raises(NormalizedReadPermanentError, match="Ambiguous"):
        select_artifact(env.norm, RAW_BUCKET)


def test_forced_fingerprint_overrides_latest_and_breaks_ties(two_artifacts):
    env, old, new = two_artifacts
    selected = select_artifact(env.norm, RAW_BUCKET, fingerprint=old.fingerprint)
    assert selected.manifest.input_fingerprint == old.fingerprint
    assert load_artifact(env.norm, RAW_BUCKET, old.fingerprint).csv_key == old.csv_key


def test_forced_fingerprint_ignores_corruption_of_other_artifacts(two_artifacts):
    env, old, new = two_artifacts
    env.norm.objects[new.manifest_key] = b"garbage"
    assert select_artifact(env.norm, RAW_BUCKET, old.fingerprint).csv_key == old.csv_key


def test_unknown_fingerprint_is_permanent(two_artifacts):
    env, *_ = two_artifacts
    with pytest.raises(NormalizedReadPermanentError, match="No committed"):
        select_artifact(env.norm, RAW_BUCKET, fingerprint="0" * 64)


@pytest.mark.parametrize("bad", ["abc", "A" * 64, "g" * 64, ""])
def test_malformed_fingerprint_is_a_usage_error(bad):
    with pytest.raises(ValueError):
        select_artifact(MemoryRawStore(), RAW_BUCKET, fingerprint=bad)


def test_csv_sha_mismatch_is_permanent():
    env = Env()
    result = env.normalize()
    data = bytearray(env.norm.get(result.csv_key))
    data[-2] ^= 1  # same length, different content
    env.norm.objects[result.csv_key] = bytes(data)
    with pytest.raises(NormalizedReadPermanentError, match="sha256"):
        load_artifact(env.norm, RAW_BUCKET)


def test_csv_length_mismatch_is_permanent():
    env = Env()
    result = env.normalize()
    env.norm.objects[result.csv_key] += b"x"
    with pytest.raises(NormalizedReadPermanentError, match="size"):
        load_artifact(env.norm, RAW_BUCKET)


def test_missing_csv_of_a_committed_manifest_is_permanent():
    env = Env()
    result = env.normalize()
    del env.norm.objects[result.csv_key]
    with pytest.raises(NormalizedReadPermanentError):
        load_artifact(env.norm, RAW_BUCKET)


def test_row_count_zero_is_rejected():
    env = Env()
    result = env.normalize()
    _, m = clone(env, result, row_count=0)
    selected = select_artifact(env.norm, RAW_BUCKET, fingerprint=m.input_fingerprint)
    with pytest.raises(NormalizedReadPermanentError, match="row_count"):
        read_artifact(env.norm, selected)


def test_coverage_from_other_than_backfill_is_rejected():
    env = Env()
    result = env.normalize()
    base = parsed(env, result)
    coverage = Coverage(date(1991, 12, 3), base.coverage.to_date)
    _, m = clone(env, result, coverage=coverage)
    selected = select_artifact(env.norm, RAW_BUCKET, fingerprint=m.input_fingerprint)
    with pytest.raises(NormalizedReadPermanentError, match="coverage.from"):
        read_artifact(env.norm, selected)


class FlakyStore(MemoryRawStore):
    def __init__(self, source, fail_on, error):
        super().__init__()
        self.objects = source.objects
        self.fail_on, self.error = fail_on, error

    def list_prefixes(self, prefix):
        if self.fail_on == "list":
            raise self.error
        return super().list_prefixes(prefix)

    def get(self, key):
        if self.fail_on == "manifest" and key.endswith("manifest.json"):
            raise self.error
        if self.fail_on == "csv" and key.endswith(".csv"):
            raise self.error
        return super().get(key)


@pytest.mark.parametrize("where", ["list", "manifest", "csv"])
def test_transient_store_errors_are_transient(where):
    env = Env()
    env.normalize()
    store = FlakyStore(env.norm, where, RawStoreTransientError("timeout"))
    with pytest.raises(NormalizedReadTransientError):
        load_artifact(store, RAW_BUCKET)


@pytest.mark.parametrize("where", ["list", "manifest", "csv"])
def test_other_store_errors_are_permanent(where):
    env = Env()
    env.normalize()
    store = FlakyStore(env.norm, where, RawStoreError("AccessDenied"))
    with pytest.raises(NormalizedReadPermanentError):
        load_artifact(store, RAW_BUCKET)


def test_reads_what_the_real_normalizer_wrote_byte_for_byte():
    env = Env()
    result = env.normalize()
    art = load_artifact(env.norm, RAW_BUCKET)
    assert art.csv_key == result.csv_key and art.manifest_key == result.manifest_key
    assert art.csv_bytes == env.norm.get(result.csv_key)
    assert (
        art.csv_bytes.splitlines()[0]
        == b"rate_date,currency_from,currency_to,rate,source_reference"
    )
    assert art.row_count == result.rows == len(art.csv_bytes.splitlines()) - 1
    # An unrelated prefix next to the layout is ignored.
    env.norm.put_once("fx_rate/source_system=superfinanciera_trm/README.txt", b"x", "text/plain")
    env.norm.put_once("fx_rate/source_system=other_source/inputs_until=2026-10-09/x/y", b"x", "t")
    assert load_artifact(env.norm, RAW_BUCKET).fingerprint == result.fingerprint

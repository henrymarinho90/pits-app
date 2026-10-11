"""Offline tests for pits.ingestion.manifest (MemoryRawStore)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from pits.ingestion.manifest import (
    MANIFEST_NAME,
    Extractor,
    FileEntry,
    Manifest,
    ManifestError,
    Query,
    SchemaColumn,
    Watermark,
    commit_order_key,
    find_latest_committed,
    list_committed,
    manifest_key,
    sha256_hex,
)
from pits.ingestion.raw_store import MemoryRawStore, batch_prefix

SS = "superfinanciera_trm"
DS = "32sa-8pi3"
B1 = "0b6f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a10"
B2 = "1c7a7d2f-4d2b-4a1f-8b62-3e5d7a9fab21"
B3 = "2d8b8e30-5e3c-4b20-9c73-4f6e8bafbc32"


def make_manifest(batch_id=B1, day=date(2026, 10, 10), finished=None, **overrides) -> Manifest:
    prefix = batch_prefix(SS, day, batch_id)
    started = overrides.get("started_at") or datetime(day.year, day.month, day.day, 12, tzinfo=UTC)
    base = {
        "source_system": SS,
        "dataset_id": DS,
        "source_url": "https://www.datos.gov.co/resource/32sa-8pi3.json",
        "license": "CC_40_BY_SA",
        "attribution": "Superintendencia Financiera de Colombia - SUPERFINANCIERA, Bogotá D.C.",
        "batch_id": batch_id,
        "extraction_date": day,
        "started_at": started,
        "finished_at": finished or started + timedelta(seconds=30),
        "extractor": Extractor("pits.sources.trm", "0.1.0"),
        "source_rows_updated_at": 1760054700,
        "app_token_used": False,
        "query": Query(order="vigenciadesde ASC, :id ASC", page_size=1000, where=None),
        "watermark": Watermark("vigenciadesde", "full", None, date(2026, 10, 10)),
        "schema": (SchemaColumn("valor", "number"), SchemaColumn("vigenciadesde", "calendar_date")),
        "row_count": 1500,
        "files": (
            FileEntry(
                prefix + "payload-00000.json", 0, 1000, 120, sha256_hex(b"a"), "application/json"
            ),
            FileEntry(
                prefix + "payload-00001.json", 1000, 500, 60, sha256_hex(b"b"), "application/json"
            ),
        ),
    }
    base.update(overrides)
    return Manifest(**base)


def commit(store: MemoryRawStore, manifest: Manifest) -> None:
    prefix = batch_prefix(manifest.source_system, manifest.extraction_date, manifest.batch_id)
    store.put_once(manifest_key(prefix), manifest.to_json(), "application/json")


def mutated(manifest: Manifest, mutate) -> bytes:
    data = json.loads(manifest.to_json())
    mutate(data)
    return json.dumps(data).encode()


def test_roundtrip_is_byte_identical():
    manifest = make_manifest()
    data = manifest.to_json()
    parsed = Manifest.from_json(data)
    assert parsed == manifest
    assert parsed.to_json() == data
    assert sha256_hex(data) == sha256_hex(manifest.to_json())


def test_json_format_is_deterministic_utf8_with_utc_z():
    data = make_manifest().to_json()
    text = data.decode("utf-8")
    assert text.endswith("}\n")
    assert "\r" not in text
    assert "Bogotá" in text  # ensure_ascii=False
    assert '"started_at": "2026-10-10T12:00:00.000000Z"' in text
    keys = list(json.loads(text))
    assert keys == sorted(keys)


def test_non_utc_timezone_is_normalized_to_utc():
    bogota = timezone(timedelta(hours=-5))
    manifest = make_manifest(
        started_at=datetime(2026, 10, 10, 7, 0, tzinfo=bogota),
        finished_at=datetime(2026, 10, 10, 7, 1, tzinfo=bogota),
    )
    assert '"started_at": "2026-10-10T12:00:00.000000Z"' in manifest.to_json().decode()


def test_sha256_hex_is_stable():
    assert sha256_hex(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_manifest_key():
    assert manifest_key("a/b/") == "a/b/" + MANIFEST_NAME


def test_naive_datetime_rejected_on_construction():
    with pytest.raises(ManifestError, match="timezone-aware"):
        make_manifest(
            started_at=datetime(2026, 10, 10, 12, 0), finished_at=datetime(2026, 10, 10, 13)
        )


def test_datetime_as_extraction_date_rejected():
    with pytest.raises(ManifestError, match="not a datetime"):
        make_manifest(extraction_date=datetime(2026, 10, 10, tzinfo=UTC))


def test_from_json_rejects_unsupported_version():
    data = mutated(make_manifest(), lambda d: d.update(manifest_version=2))
    with pytest.raises(ManifestError, match="manifest_version"):
        Manifest.from_json(data)


def test_from_json_rejects_naive_timestamp():
    data = mutated(make_manifest(), lambda d: d.update(started_at="2026-10-10T12:00:00.000000"))
    with pytest.raises(ManifestError, match="started_at"):
        Manifest.from_json(data)


def test_from_json_rejects_incoherent_row_count():
    data = mutated(make_manifest(), lambda d: d.update(row_count=1499))
    with pytest.raises(ManifestError, match="row_count"):
        Manifest.from_json(data)


def test_from_json_rejects_key_outside_batch_prefix():
    def mutate(d):
        d["files"][0]["key"] = f"{SS}/extraction_date=2026-10-10/batch_id={B2}/payload-00000.json"

    with pytest.raises(ManifestError, match="outside the batch prefix"):
        Manifest.from_json(mutated(make_manifest(), mutate))


def test_from_json_rejects_unknown_and_missing_keys_and_bad_types():
    with pytest.raises(ManifestError, match="unexpected"):
        Manifest.from_json(mutated(make_manifest(), lambda d: d.update(extra=1)))
    with pytest.raises(ManifestError, match="missing"):
        Manifest.from_json(mutated(make_manifest(), lambda d: d.pop("license")))
    with pytest.raises(ManifestError, match="app_token_used"):
        Manifest.from_json(mutated(make_manifest(), lambda d: d.update(app_token_used="no")))
    with pytest.raises(ManifestError, match="row_count"):
        Manifest.from_json(mutated(make_manifest(), lambda d: d.update(row_count=True)))


def test_from_json_rejects_invalid_mode_sha_and_garbage():
    def bad_mode(d):
        d["watermark"]["mode"] = "lookback"

    with pytest.raises(ManifestError, match="mode"):
        Manifest.from_json(mutated(make_manifest(), bad_mode))

    def bad_sha(d):
        d["files"][0]["sha256"] = "xyz"

    with pytest.raises(ManifestError, match="sha256"):
        Manifest.from_json(mutated(make_manifest(), bad_sha))
    with pytest.raises(ManifestError, match="valid UTF-8 JSON"):
        Manifest.from_json(b"{not json")
    with pytest.raises(ManifestError, match="must be an object"):
        Manifest.from_json(b"[]")


def test_empty_batch_is_valid():
    manifest = make_manifest(row_count=0, files=())
    assert Manifest.from_json(manifest.to_json()) == manifest


def test_find_latest_without_batches_is_none():
    assert find_latest_committed(MemoryRawStore(), SS, DS) is None


def test_find_latest_ignores_orphan_batch():
    store = MemoryRawStore()
    orphan = batch_prefix(SS, date(2026, 10, 10), B1)
    store.put_once(orphan + "payload-00000.json", b"[]", "application/json")
    assert find_latest_committed(store, SS, DS) is None


def test_find_latest_picks_newest_partition_with_a_manifest():
    store = MemoryRawStore()
    old = make_manifest(B1, date(2026, 10, 8))
    commit(store, old)
    # newest partition only has an orphan -> fall back to the older committed one
    store.put_once(batch_prefix(SS, date(2026, 10, 10), B2) + "payload-00000.json", b"[]", "a/b")
    assert find_latest_committed(store, SS, DS) == old
    newer = make_manifest(B3, date(2026, 10, 9))
    commit(store, newer)
    assert find_latest_committed(store, SS, DS) == newer


def test_find_latest_same_day_picks_greatest_finished_at():
    store = MemoryRawStore()
    early = make_manifest(B1)
    late = make_manifest(B2, finished=early.finished_at + timedelta(hours=1))
    commit(store, late)
    commit(store, early)
    assert find_latest_committed(store, SS, DS) == late


def test_find_latest_corrupt_manifest_is_loud():
    store = MemoryRawStore()
    store.put_once(manifest_key(batch_prefix(SS, date(2026, 10, 10), B1)), b"{oops", "a/b")
    with pytest.raises(ManifestError, match="manifest.json"):
        find_latest_committed(store, SS, DS)


def test_find_latest_other_dataset_is_loud():
    store = MemoryRawStore()
    commit(store, replace(make_manifest(), dataset_id="zzzz-0000"))
    with pytest.raises(ManifestError, match="expected"):
        find_latest_committed(store, SS, DS)


def test_find_latest_manifest_in_wrong_location_is_loud():
    store = MemoryRawStore()
    wrong = batch_prefix(SS, date(2026, 10, 10), B2)
    store.put_once(manifest_key(wrong), make_manifest(B1).to_json(), "application/json")
    with pytest.raises(ManifestError, match="do not match its location"):
        find_latest_committed(store, SS, DS)


def test_find_latest_unexpected_prefixes_are_loud():
    store = MemoryRawStore()
    store.put_once(f"{SS}/junk/file.json", b"x", "a/b")
    with pytest.raises(ManifestError, match="Unexpected prefix"):
        find_latest_committed(store, SS, DS)
    store = MemoryRawStore()
    store.put_once(f"{SS}/extraction_date=2026-10-10/oops/file.json", b"x", "a/b")
    with pytest.raises(ManifestError, match="Unexpected prefix"):
        find_latest_committed(store, SS, DS)


def test_find_latest_does_not_see_other_source_systems():
    store = MemoryRawStore()
    store.put_once("other_source/junk/file.json", b"x", "a/b")
    assert find_latest_committed(store, SS, DS) is None


def wm(mode, frm, to):
    return Watermark("vigenciadesde", mode, frm, to)


D8, D9, D10 = date(2026, 10, 8), date(2026, 10, 9), date(2026, 10, 10)


def test_empty_incremental_carries_watermark_forward():
    manifest = make_manifest(row_count=0, files=(), watermark=wm("incremental", D8, D8))
    assert Manifest.from_json(manifest.to_json()) == manifest


@pytest.mark.parametrize(
    ("watermark", "row_count", "files", "match"),
    [
        (wm("incremental", D8, None), 0, (), "to_observed"),
        (wm("incremental", D8, D9), 0, (), "carry the watermark forward"),
        (wm("incremental", D9, D8), 1500, None, "before from_exclusive"),
        (wm("incremental", None, D10), 1500, None, "requires watermark.from_exclusive"),
        (wm("full", D8, D10), 1500, None, "full mode must not"),
        (wm("since", None, D10), 1500, None, "requires watermark.from_exclusive"),
        (wm("since", D8, None), 1500, None, "requires watermark.to_observed"),
        (wm("full", None, None), 1500, None, "requires watermark.to_observed"),
    ],
)
def test_watermark_invariants(watermark, row_count, files, match):
    overrides = {"watermark": watermark}
    if files is not None:
        overrides.update(row_count=row_count, files=files)
    with pytest.raises(ManifestError, match=match):
        make_manifest(**overrides)


def test_empty_since_and_full_may_have_no_to_observed():
    make_manifest(row_count=0, files=(), watermark=wm("since", D8, None))
    make_manifest(row_count=0, files=(), watermark=wm("full", None, None))


def test_extraction_date_must_match_started_at_utc_date():
    with pytest.raises(ManifestError, match="UTC date of started_at"):
        make_manifest(extraction_date=D9)


def test_non_contiguous_offsets_rejected():
    base = make_manifest()
    bad = (base.files[0], replace(base.files[1], offset=999))
    with pytest.raises(ManifestError, match="Non-contiguous"):
        make_manifest(files=bad)


def test_page_size_must_be_positive():
    with pytest.raises(ManifestError, match="page_size"):
        make_manifest(query=Query("vigenciadesde ASC", 0, None))


def test_schema_names_must_be_unique_and_non_empty():
    with pytest.raises(ManifestError, match="schema column names"):
        make_manifest(schema=(SchemaColumn("a", "text"), SchemaColumn("a", "text")))
    with pytest.raises(ManifestError, match="schema column names"):
        make_manifest(schema=(SchemaColumn("", "text"),))


def test_finished_before_started_rejected():
    started = datetime(2026, 10, 10, 12, tzinfo=UTC)
    with pytest.raises(ManifestError, match="finished_at"):
        make_manifest(started_at=started, finished_at=started - timedelta(seconds=1))


def test_duplicate_keys_rejected():
    first = make_manifest().files[0]
    with pytest.raises(ManifestError, match="duplicate"):
        make_manifest(files=(first, replace(first, offset=1000)), row_count=2000)


def test_negative_number_rejected():
    first = make_manifest().files[0]
    with pytest.raises(ManifestError, match="Negative"):
        make_manifest(files=(replace(first, size_bytes=-1),), row_count=1000)


def test_manifest_json_inside_files_rejected():
    prefix = batch_prefix(SS, D10, B1)
    entry = FileEntry(prefix + MANIFEST_NAME, 0, 5, 10, sha256_hex(b"a"), "application/json")
    with pytest.raises(ManifestError, match="outside the batch prefix"):
        make_manifest(files=(entry,), row_count=5)


def test_constructor_rejects_version_2():
    with pytest.raises(ManifestError, match="manifest_version"):
        make_manifest(manifest_version=2)


def test_constructor_wraps_invalid_batch_id():
    with pytest.raises(ManifestError, match="batch_id"):
        Manifest(**{**make_manifest().__dict__, "batch_id": "nope", "files": (), "row_count": 0})


def test_from_json_rejects_non_utf8_bytes():
    with pytest.raises(ManifestError, match="UTF-8"):
        Manifest.from_json(b"\xff\xfe{}")


def test_find_latest_after_empty_incremental_keeps_watermark():
    store = MemoryRawStore()
    commit(store, make_manifest(B1, D8, watermark=wm("full", None, D8)))
    empty = make_manifest(B2, D9, row_count=0, files=(), watermark=wm("incremental", D8, D8))
    commit(store, empty)
    latest = find_latest_committed(store, SS, DS)
    assert latest == empty
    assert latest.watermark.to_observed == D8


def test_find_latest_same_finished_at_tie_breaks_by_batch_id():
    store = MemoryRawStore()
    commit(store, make_manifest(B1))
    commit(store, make_manifest(B2))
    assert find_latest_committed(store, SS, DS).batch_id == B2


def test_find_latest_invalid_partition_date_is_loud():
    store = MemoryRawStore()
    store.put_once(f"{SS}/extraction_date=2026-13-45/batch_id={B1}/manifest.json", b"{}", "a/b")
    with pytest.raises(ManifestError, match="ISO date"):
        find_latest_committed(store, SS, DS)


class ShuffledStore(MemoryRawStore):
    """list_prefixes returns descending order to prove no dependence on LIST order."""

    def list_prefixes(self, prefix):
        return sorted(super().list_prefixes(prefix), reverse=True)


class CountingStore(MemoryRawStore):
    def __init__(self):
        super().__init__()
        self.gets: list[str] = []

    def get(self, key):
        self.gets.append(key)
        return super().get(key)


def test_commit_order_key_fields():
    m = make_manifest(B2)
    assert commit_order_key(m) == (m.extraction_date, m.finished_at, B2)


def test_list_committed_empty_and_orphans_ignored():
    store = MemoryRawStore()
    assert list_committed(store, SS, DS) == ()
    store.put_once(batch_prefix(SS, date(2026, 10, 10), B1) + "payload-00000.json", b"[]", "a/b")
    assert list_committed(store, SS, DS) == ()


def test_list_committed_orders_by_commit_order_despite_shuffled_list():
    store = ShuffledStore()
    a = make_manifest(B3, date(2026, 10, 8))
    b = make_manifest(B1, date(2026, 10, 9))
    c = make_manifest(B2, date(2026, 10, 9))  # same finished_at as b -> batch_id tie-break
    d = make_manifest(B1, date(2026, 10, 10))
    for m in (d, b, a, c):
        commit(store, m)
    assert list_committed(store, SS, DS) == (a, b, c, d)
    assert list_committed(store, SS, DS)[-1] == find_latest_committed(store, SS, DS)


def test_list_committed_last_equals_find_latest_same_day_finished_at():
    store = ShuffledStore()
    early = make_manifest(B2)
    late = make_manifest(B1, finished=early.finished_at + timedelta(hours=1))
    commit(store, early)
    commit(store, late)
    assert list_committed(store, SS, DS) == (early, late)
    assert list_committed(store, SS, DS)[-1] == find_latest_committed(store, SS, DS) == late


def test_list_committed_corrupt_manifest_in_old_partition_is_loud():
    store = MemoryRawStore()
    store.put_once(manifest_key(batch_prefix(SS, date(2026, 10, 1), B1)), b"{oops", "a/b")
    commit(store, make_manifest(B2, date(2026, 10, 10)))
    with pytest.raises(ManifestError, match="manifest.json"):
        list_committed(store, SS, DS)
    # find_latest keeps reading only the newest partition with a committed batch
    assert find_latest_committed(store, SS, DS).batch_id == B2


def test_list_committed_other_dataset_is_loud():
    store = MemoryRawStore()
    commit(store, replace(make_manifest(), dataset_id="zzzz-0000"))
    with pytest.raises(ManifestError, match="expected"):
        list_committed(store, SS, DS)


def test_list_committed_location_mismatch_is_loud():
    store = MemoryRawStore()
    wrong_batch = batch_prefix(SS, date(2026, 10, 10), B2)
    store.put_once(manifest_key(wrong_batch), make_manifest(B1).to_json(), "application/json")
    with pytest.raises(ManifestError, match="do not match its location"):
        list_committed(store, SS, DS)
    store = MemoryRawStore()
    wrong_part = batch_prefix(SS, date(2026, 10, 9), B1)
    store.put_once(manifest_key(wrong_part), make_manifest(B1).to_json(), "application/json")
    with pytest.raises(ManifestError, match="do not match its location"):
        list_committed(store, SS, DS)


def test_list_committed_version_not_one_is_loud():
    store = MemoryRawStore()
    key = manifest_key(batch_prefix(SS, date(2026, 10, 10), B1))
    data = mutated(make_manifest(), lambda d: d.__setitem__("manifest_version", 2))
    store.put_once(key, data, "application/json")
    with pytest.raises(ManifestError, match="manifest_version"):
        list_committed(store, SS, DS)


def test_list_committed_unexpected_prefixes_are_loud():
    store = MemoryRawStore()
    store.put_once(f"{SS}/junk/file.json", b"x", "a/b")
    with pytest.raises(ManifestError, match="Unexpected prefix"):
        list_committed(store, SS, DS)
    store = MemoryRawStore()
    store.put_once(f"{SS}/extraction_date=2026-10-10/oops/file.json", b"x", "a/b")
    with pytest.raises(ManifestError, match="Unexpected prefix"):
        list_committed(store, SS, DS)


def test_find_latest_reads_only_newest_committed_partition():
    store = CountingStore()
    commit(store, make_manifest(B1, date(2026, 10, 8)))
    commit(store, make_manifest(B2, date(2026, 10, 9)))
    store.gets.clear()
    assert find_latest_committed(store, SS, DS).batch_id == B2
    assert len(store.gets) == 1

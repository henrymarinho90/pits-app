"""Offline tests for pits.ingestion.batch_reader."""

from __future__ import annotations

import json
from datetime import date

import pytest
from ingestion_helpers import B1, SS, CountingStore, make_manifest

from pits.ingestion.batch_reader import PayloadIntegrityError, iter_verified_pages
from pits.ingestion.manifest import FileEntry, ManifestError, sha256_hex
from pits.ingestion.raw_store import MemoryRawStore, RawStoreTransientError, batch_prefix

PREFIX = batch_prefix(SS, date(2026, 10, 10), B1)
PAGE0 = json.dumps([{"valor": "1"}, {"valor": "2"}]).encode()
PAGE1 = json.dumps([{"valor": "3"}]).encode()


def entry(i, body, **kw):
    base = {
        "key": f"{PREFIX}payload-{i:05d}.json",
        "offset": 0 if i == 0 else 2,
        "row_count": 2 if i == 0 else 1,
        "size_bytes": len(body),
        "sha256": sha256_hex(body),
        "content_type": "application/json",
    }
    base.update(kw)
    return FileEntry(**base)


def fill(store, bodies=(PAGE0, PAGE1)):
    for i, body in enumerate(bodies):
        store.put_once(f"{PREFIX}payload-{i:05d}.json", body, "application/json")
    return store


def manifest_of(files):
    return make_manifest(B1, row_count=sum(f.row_count for f in files), files=files)


def two_page_manifest():
    return manifest_of((entry(0, PAGE0), entry(1, PAGE1)))


def test_yields_verified_pages_in_order():
    manifest = two_page_manifest()
    pages = list(iter_verified_pages(fill(MemoryRawStore()), manifest))
    assert [p.entry for p in pages] == list(manifest.files)
    assert pages[0].body == PAGE0
    assert pages[0].rows == [{"valor": "1"}, {"valor": "2"}]
    assert pages[1].rows == [{"valor": "3"}]


def test_empty_batch_yields_nothing():
    manifest = make_manifest(B1, row_count=0, files=())
    assert list(iter_verified_pages(MemoryRawStore(), manifest)) == []


def test_missing_payload_is_permanent_with_key():
    store = fill(MemoryRawStore(), bodies=(PAGE0,))
    it = iter_verified_pages(store, two_page_manifest())
    next(it)
    with pytest.raises(PayloadIntegrityError, match=r"payload-00001\.json.*missing"):
        next(it)


def test_payload_integrity_error_is_manifest_error():
    assert issubclass(PayloadIntegrityError, ManifestError)


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"size_bytes": 1}, "size mismatch"),
        ({"sha256": "0" * 64}, "sha256 mismatch"),
        ({"row_count": 3}, "row_count mismatch"),
    ],
)
def test_entry_mismatch_is_permanent(override, match):
    second = entry(1, PAGE1, offset=override.get("row_count", 2))  # keep offsets contiguous
    manifest = manifest_of((entry(0, PAGE0, **override), second))
    with pytest.raises(PayloadIntegrityError, match=match) as exc:
        list(iter_verified_pages(fill(MemoryRawStore()), manifest))
    assert "payload-00000.json" in str(exc.value)
    assert "valor" not in str(exc.value)


def test_same_size_different_bytes_fails_sha():
    tampered = PAGE0.replace(b"1", b"9")
    assert len(tampered) == len(PAGE0)
    store = fill(MemoryRawStore(), bodies=(tampered, PAGE1))
    with pytest.raises(PayloadIntegrityError, match="sha256 mismatch"):
        list(iter_verified_pages(store, two_page_manifest()))


@pytest.mark.parametrize("body", [b'{"a": 1}', b'"text"', b"[1, 2]", b'[{"a": 1}, 3]'])
def test_non_array_of_objects_is_permanent(body):
    e = entry(0, body, row_count=1)
    store = MemoryRawStore()
    store.put_once(e.key, body, "application/json")
    with pytest.raises(PayloadIntegrityError, match="array of objects"):
        list(iter_verified_pages(store, manifest_of((e,))))


def test_non_utf8_payload_is_permanent():
    body = bytes([0xFF])
    e = entry(0, body, row_count=0)
    store = MemoryRawStore()
    store.put_once(e.key, body, "application/json")
    with pytest.raises(PayloadIntegrityError, match="not valid"):
        list(iter_verified_pages(store, manifest_of((e,))))


def test_invalid_json_is_permanent():
    body = b"{not json"
    e = entry(0, body, row_count=0)
    store = MemoryRawStore()
    store.put_once(e.key, body, "application/json")
    with pytest.raises(PayloadIntegrityError, match="not valid"):
        list(iter_verified_pages(store, manifest_of((e,))))


def test_reading_is_lazy_one_get_per_page():
    store = fill(CountingStore())
    it = iter_verified_pages(store, two_page_manifest())
    assert store.gets == []
    next(it)
    assert len(store.gets) == 1
    next(it)
    assert len(store.gets) == 2


def test_transient_error_propagates_unchanged():
    class Flaky(MemoryRawStore):
        def get(self, key):
            raise RawStoreTransientError("boom")

    with pytest.raises(RawStoreTransientError):
        next(iter_verified_pages(Flaky(), two_page_manifest()))

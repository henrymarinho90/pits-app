"""Golden constants of the TRM normalization: a refactor must not change a single byte (D98)."""

from __future__ import annotations

import ast
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from trm_helpers import B1, put_raw_batch, raw_row

from pits.ingestion.manifest import sha256_hex
from pits.ingestion.raw_store import MemoryRawStore, RawStoreTransientError
from pits.normalized.commit import NormalizedOutcome, commit_objects
from pits.normalized.manifest import NormalizedManifest
from pits.sources.trm.contract import BACKFILL_FROM
from pits.sources.trm.normalize import normalize_trm

GOLDEN_CSV_SHA256 = "e0b99addbbc2ec2961c1c6e5ad4808865f1d5088ab89abf108c94100fd60416f"
GOLDEN_MANIFEST_SHA256 = "d0dde4283c84b0cc266d443e0f055056b54718d5978fddebf90a483723806380"
GOLDEN_FINGERPRINT = "d474905b6c1a99cf3fe00dbb7f2c64ddc2d525dd96cfb809c024db279a1622fb"


def test_trm_normalization_is_byte_identical_to_golden():
    raw = MemoryRawStore()
    put_raw_batch(
        raw,
        B1,
        date(2026, 10, 9),
        "full",
        [
            raw_row(BACKFILL_FROM, date(2026, 10, 9), "3000.5"),
            raw_row(date(2026, 10, 10), date(2026, 10, 13), "3194.44"),
        ],
    )
    norm = MemoryRawStore()
    result = normalize_trm(raw, norm, raw_bucket="pits-raw")
    manifest_bytes = norm.get(result.manifest_key)
    assert NormalizedManifest.from_json(manifest_bytes).input_fingerprint == result.fingerprint
    assert sha256_hex(norm.get(result.csv_key)) == GOLDEN_CSV_SHA256
    assert sha256_hex(manifest_bytes) == GOLDEN_MANIFEST_SHA256
    assert result.fingerprint == GOLDEN_FINGERPRINT


def test_fingerprint_module_does_not_import_pits_sources():
    path = Path(__file__).parents[2] / "src" / "pits" / "normalized" / "fingerprint.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        assert not any(n == "pits.sources" or n.startswith("pits.sources.") for n in names)


def test_fingerprint_import_does_not_load_pits_sources():
    code = (
        "import sys, pits.normalized.fingerprint; "
        "print([m for m in sys.modules if m == 'pits.sources' or m.startswith('pits.sources.')])"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=False
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "[]", f"pits.sources loaded: {proc.stdout} {proc.stderr}"


OBJS = [("a/1.csv", b"1", "text/csv"), ("a/2.csv", b"2", "text/csv")]


def test_commit_objects_writes_all_objects_then_manifest_last():
    store = MemoryRawStore()
    assert commit_objects(store, OBJS, "a/manifest.json", b"{}") is NormalizedOutcome.CREATED
    assert list(store.objects) == ["a/1.csv", "a/2.csv", "a/manifest.json"]
    assert (
        commit_objects(store, OBJS, "a/manifest.json", b"{}") is NormalizedOutcome.ALREADY_PRESENT
    )


def test_commit_objects_accepts_mapping():
    store = MemoryRawStore()
    mapping = {k: (b, ct) for k, b, ct in OBJS}
    assert commit_objects(store, mapping, "a/manifest.json", b"{}") is NormalizedOutcome.CREATED
    assert list(store.objects)[-1] == "a/manifest.json" and len(store.objects) == 3


class FailOnSecondPut(MemoryRawStore):
    def __init__(self):
        super().__init__()
        self.calls = 0
        self.armed = True

    def put_once(self, key, body, content_type):
        self.calls += 1
        if self.armed and self.calls == 2:
            raise RawStoreTransientError("boom")
        return super().put_once(key, body, content_type)


def test_commit_objects_crash_midway_leaves_no_manifest_and_retry_completes():
    store = FailOnSecondPut()
    with pytest.raises(RawStoreTransientError):
        commit_objects(store, OBJS, "a/manifest.json", b"{}")
    assert "a/manifest.json" not in store.objects and list(store.objects) == ["a/1.csv"]
    store.armed = False
    assert commit_objects(store, OBJS, "a/manifest.json", b"{}") is NormalizedOutcome.CREATED
    assert list(store.objects) == ["a/1.csv", "a/2.csv", "a/manifest.json"]


@pytest.mark.parametrize(
    "objs",
    [
        [],
        [("a/manifest.json", b"x", "text/csv")],
        [("a/1.csv", b"1", "text/csv"), ("a/1.csv", b"2", "text/csv")],
    ],
    ids=["empty", "manifest_key_among_objects", "duplicate_keys"],
)
def test_commit_objects_validates_before_writing(objs):
    store = MemoryRawStore()
    with pytest.raises(ValueError):
        commit_objects(store, objs, "a/manifest.json", b"{}")
    assert store.objects == {}

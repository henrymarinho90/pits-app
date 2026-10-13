"""Contract test of `pits storage orphans` against a live local S3 (SeaweedFS), read-only (D107).

Run: uv run --env-file ../pits-app/.env pytest -m contract -q -k orphans
The reader identity does not exist until S4, so the test maps the admin credentials onto the
client and swaps the settings loader (contract buckets are rejected by load_storage_settings on
purpose, D61). The inventory itself only lists; the test uses the admin client to seed objects.
"""

from __future__ import annotations

import pytest
from botocore.client import BaseClient
from s3_helpers import BucketFactory
from typer.testing import CliRunner

from pits.cli import app
from pits.storage import cli as storage_cli
from pits.storage.settings import StorageSettings

pytestmark = pytest.mark.contract

B_OK = "0b6f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a10"
B_ORPHAN = "1c7f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a11"
FP_OK, FP_ORPHAN = "a" * 64, "b" * 64


def test_inventory_reports_only_the_orphans(
    monkeypatch: pytest.MonkeyPatch,
    s3: BaseClient,
    make_bucket: BucketFactory,
) -> None:
    raw, norm = make_bucket(), make_bucket()
    ok = f"trm_soda/extraction_date=2026-10-01/batch_id={B_OK}/"
    orphan = f"trm_soda/extraction_date=2026-10-01/batch_id={B_ORPHAN}/"
    fx_ok = f"fx_rate/source_system=trm_soda/inputs_until=2026-10-01/fingerprint={FP_OK}/"
    fx_orphan = f"fx_rate/source_system=trm_soda/inputs_until=2026-10-01/fingerprint={FP_ORPHAN}/"
    for key, body in [
        (ok + "data.csv", b"abc"),
        (ok + "manifest.json", b"{}"),
        (orphan + "data.csv", b"abcdef"),
        (orphan + "data2.csv", b"xyz"),
        ("stray.txt", b"?"),
    ]:
        s3.put_object(Bucket=raw, Key=key, Body=body)
    for key, body in [
        (fx_ok + "fx_rate.csv", b"1"),
        (fx_ok + "manifest.json", b"{}"),
        (fx_orphan + "fx_rate.csv", b"12345"),
    ]:
        s3.put_object(Bucket=norm, Key=key, Body=body)

    settings = StorageSettings("http://127.0.0.1:9", "unused", "unused", "us-east-1", raw, norm)

    def fake_loader(env: object, *, identity: str) -> StorageSettings:
        assert identity == "reader"
        return settings

    monkeypatch.setattr(storage_cli, "load_storage_settings", fake_loader)
    monkeypatch.setattr(storage_cli, "client_factory", lambda _settings: s3)

    result = CliRunner().invoke(app, ["storage", "orphans"])

    assert result.exit_code == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0].startswith(f"orphan bucket={raw} prefix={orphan} objects=2 bytes=9 newest=")
    assert f"unexpected bucket={raw} key=stray.txt" in lines
    assert f"bucket={raw} groups=2 committed=1 orphans=1 orphan_bytes=9 unexpected=1" in lines
    assert any(
        line.startswith(f"orphan bucket={norm} prefix={fx_orphan} objects=1 bytes=5 newest=")
        for line in lines
    )
    assert f"bucket={norm} groups=2 committed=1 orphans=1 orphan_bytes=5 unexpected=0" in lines
    # Read-only: nothing was added or removed by the inventory.
    assert len(s3.list_objects_v2(Bucket=raw)["Contents"]) == 5
    assert len(s3.list_objects_v2(Bucket=norm)["Contents"]) == 3

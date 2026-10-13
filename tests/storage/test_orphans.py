"""Offline tests of the orphan inventory (D107): Stubber allows ONLY list_objects_v2."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from botocore.client import BaseClient
from botocore.exceptions import EndpointConnectionError
from botocore.stub import Stubber
from typer.testing import CliRunner

from pits.cli import app
from pits.storage import cli as storage_cli
from pits.storage.client import build_s3_client
from pits.storage.orphans import (
    NORMALIZED_LAYOUT,
    RAW_LAYOUT,
    OrphansError,
    format_timestamp,
    scan_bucket,
)
from pits.storage.settings import StorageSettings

runner = CliRunner()

READER_KEY = "READERKEYEXAMPLE0001"
READER_SECRET = "reader-secret-value-0123456789-abcdef"
ENV = {
    "S3_ENDPOINT_URL": "http://127.0.0.1:9",
    "S3_RAW_BUCKET": "pits-raw",
    "PITS_S3_READER_ACCESS_KEY_ID": READER_KEY,
    "PITS_S3_READER_SECRET_ACCESS_KEY": READER_SECRET,
}
RAW, NORM = "pits-raw", "pits-normalized"
B1 = "0b6f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a10"
B2 = "1c7f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a11"
B3 = "2d8f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a12"
FP1, FP2, FP3 = "a" * 64, "b" * 64, "c" * 64
T1 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
T2 = datetime(2026, 10, 2, 13, 30, tzinfo=UTC)


def _raw(batch: str, day: str = "2026-10-01") -> str:
    return f"trm_soda/extraction_date={day}/batch_id={batch}/"


def _fx(fp: str) -> str:
    return f"fx_rate/source_system=trm_soda/inputs_until=2026-10-01/fingerprint={fp}/"


def _fleet(fp: str) -> str:
    return (
        "vehicle_fleet_snapshot/source_system=runt_open/publication_month=2026-09/"
        f"fingerprint={fp}/"
    )


def _obj(key: str, size: int = 10, modified: datetime = T1) -> dict[str, Any]:
    return {"Key": key, "Size": size, "LastModified": modified}


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "S3_NORMALIZED_BUCKET",
        "S3_REGION",
        "S3_ACCESS_KEY_ID",
        "S3_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)


def _client() -> BaseClient:
    return build_s3_client(
        StorageSettings(ENV["S3_ENDPOINT_URL"], READER_KEY, READER_SECRET, "us-east-1", RAW)
    )


def _run(monkeypatch: pytest.MonkeyPatch, stubber: Stubber, client: BaseClient) -> Any:
    monkeypatch.setattr(storage_cli, "client_factory", lambda settings: client)
    result = runner.invoke(app, ["storage", "orphans"])
    stubber.assert_no_pending_responses()
    return result


def _list(stubber: Stubber, bucket: str, contents: list[dict[str, Any]], **extra: Any) -> None:
    response: dict[str, Any] = {"Contents": contents, **extra} if contents else {}
    stubber.add_response("list_objects_v2", response, {"Bucket": bucket})


def test_raw_mixed_committed_and_orphans(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    with Stubber(client) as stubber:
        _list(
            stubber,
            RAW,
            [
                _obj(_raw(B1) + "manifest.json", 5, T2),
                _obj(_raw(B1) + "payload-0001.csv", 100),
                _obj(_raw(B2) + "payload-0001.csv", 70, T1),
                _obj(_raw(B2) + "payload-0002.csv", 30, T2),
                _obj(_raw(B3, "2026-10-02") + "manifest.json", 4),
            ],
        )
        _list(stubber, NORM, [])
        result = _run(monkeypatch, stubber, client)
    assert result.exit_code == 0, result.stderr
    assert result.stdout.splitlines() == [
        f"orphan bucket=pits-raw prefix={_raw(B2)} objects=2 bytes=100 "
        "newest=2026-10-02T13:30:00+00:00",
        "bucket=pits-raw groups=3 committed=2 orphans=1 orphan_bytes=100 unexpected=0",
        "bucket=pits-normalized groups=0 committed=0 orphans=0 orphan_bytes=0 unexpected=0",
    ]
    assert result.stderr == ""


def test_normalized_fx_and_fleet(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    with Stubber(client) as stubber:
        _list(stubber, RAW, [])
        _list(
            stubber,
            NORM,
            [
                _obj(_fx(FP1) + "fx_rate.csv", 50),
                _obj(_fx(FP1) + "manifest.json", 5),
                _obj(_fx(FP2) + "fx_rate.csv", 60),
                _obj(_fleet(FP1) + "part-00001.csv", 900),
                _obj(_fleet(FP3) + "manifest.json", 8),
                _obj(_fleet(FP3) + "part-00001.csv", 800),
            ],
        )
        result = _run(monkeypatch, stubber, client)
    assert result.exit_code == 0, result.stderr
    assert result.stdout.splitlines() == [
        "bucket=pits-raw groups=0 committed=0 orphans=0 orphan_bytes=0 unexpected=0",
        f"orphan bucket=pits-normalized prefix={_fx(FP2)} objects=1 bytes=60 "
        "newest=2026-10-01T12:00:00+00:00",
        f"orphan bucket=pits-normalized prefix={_fleet(FP1)} objects=1 bytes=900 "
        "newest=2026-10-01T12:00:00+00:00",
        "bucket=pits-normalized groups=4 committed=2 orphans=2 orphan_bytes=960 unexpected=0",
    ]


def test_unexpected_keys_are_counted_and_capped_at_20(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    stray = [_obj(f"stray/file-{i:02d}.txt") for i in range(25)]
    with Stubber(client) as stubber:
        _list(stubber, RAW, [*stray, _obj(_raw(B1) + "manifest.json")])
        _list(stubber, NORM, [_obj("fx_rate/loose.csv"), _obj(_fx("z" * 64) + "x.csv")])
        result = _run(monkeypatch, stubber, client)
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    unexpected_raw = [line for line in lines if line.startswith("unexpected bucket=pits-raw")]
    assert len(unexpected_raw) == 21  # 20 samples + the 'more' line
    assert unexpected_raw[0] == "unexpected bucket=pits-raw key=stray/file-00.txt"
    assert unexpected_raw[-1] == "unexpected bucket=pits-raw more=5"
    assert "bucket=pits-raw groups=1 committed=1 orphans=0 orphan_bytes=0 unexpected=25" in lines
    expected_norm = (
        "bucket=pits-normalized groups=0 committed=0 orphans=0 orphan_bytes=0 unexpected=2"
    )
    assert expected_norm in lines


def test_pagination_with_continuation_token_and_group_across_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client()
    with Stubber(client) as stubber:
        stubber.add_response(
            "list_objects_v2",
            {
                "Contents": [_obj(_raw(B1) + "manifest.json", 3)],
                "IsTruncated": True,
                "NextContinuationToken": "tok-1",
            },
            {"Bucket": RAW},
        )
        stubber.add_response(
            "list_objects_v2",
            {
                "Contents": [
                    _obj(_raw(B1) + "payload-0001.csv", 1),
                    _obj(_raw(B1) + "payload-0002.csv", 2),
                    _obj(_raw(B2) + "payload-0001.csv", 4),
                ]
            },
            {"Bucket": RAW, "ContinuationToken": "tok-1"},
        )
        _list(stubber, NORM, [])
        result = _run(monkeypatch, stubber, client)
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines[0].startswith(f"orphan bucket=pits-raw prefix={_raw(B2)} objects=1 bytes=4")
    assert lines[1] == "bucket=pits-raw groups=2 committed=1 orphans=1 orphan_bytes=4 unexpected=0"


def test_empty_buckets(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    with Stubber(client) as stubber:
        _list(stubber, RAW, [])
        _list(stubber, NORM, [])
        result = _run(monkeypatch, stubber, client)
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "bucket=pits-raw groups=0 committed=0 orphans=0 orphan_bytes=0 unexpected=0",
        "bucket=pits-normalized groups=0 committed=0 orphans=0 orphan_bytes=0 unexpected=0",
    ]


def test_access_denied_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    with Stubber(client) as stubber:
        stubber.add_client_error("list_objects_v2", "AccessDenied", http_status_code=403)
        result = _run(monkeypatch, stubber, client)
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.startswith("error: ") and "pits-raw" in result.stderr
    assert READER_SECRET not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr


def test_5xx_exits_3(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    with Stubber(client) as stubber:
        stubber.add_client_error("list_objects_v2", "InternalError", http_status_code=500)
        result = _run(monkeypatch, stubber, client)
    assert result.exit_code == 3
    assert result.stderr.startswith("error: ")


def test_connection_error_exits_3_without_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    class Failing:
        def list_objects_v2(self, **kwargs: Any) -> Any:
            raise EndpointConnectionError(endpoint_url=f"http://x?k={READER_SECRET}")

    monkeypatch.setattr(storage_cli, "client_factory", lambda settings: Failing())
    result = runner.invoke(app, ["storage", "orphans"])
    assert result.exit_code == 3
    assert "EndpointConnectionError" in result.stderr
    assert READER_SECRET not in result.stdout + result.stderr


def test_missing_reader_variables_exit_1_naming_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PITS_S3_READER_SECRET_ACCESS_KEY")
    result = runner.invoke(app, ["storage", "orphans"])
    assert result.exit_code == 1
    assert "PITS_S3_READER_SECRET_ACCESS_KEY" in result.stderr
    assert result.stdout == ""


def test_admin_credentials_are_not_a_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PITS_S3_READER_ACCESS_KEY_ID")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "AKIDEXAMPLE0001")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "admin-secret-value-xyz")
    result = runner.invoke(app, ["storage", "orphans"])
    assert result.exit_code == 1
    assert "PITS_S3_READER_ACCESS_KEY_ID" in result.stderr
    assert "admin-secret-value-xyz" not in result.stdout + result.stderr


def test_secrets_absent_from_successful_output(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    with Stubber(client) as stubber:
        _list(stubber, RAW, [_obj(_raw(B1) + "a.csv")])
        _list(stubber, NORM, [])
        result = _run(monkeypatch, stubber, client)
    combined = result.stdout + result.stderr
    assert READER_SECRET not in combined and READER_KEY not in combined


def test_stubber_rejects_any_write_operation() -> None:
    """With no put/delete queued, the Stubber fails them: proves the guard used above."""
    client = _client()
    with Stubber(client):
        with pytest.raises(Exception):  # noqa: B017, PT011  (UnStubbedResponseError)
            client.put_object(Bucket=RAW, Key="x", Body=b"")
        with pytest.raises(Exception):  # noqa: B017, PT011
            client.delete_object(Bucket=RAW, Key="x")


def test_scan_bucket_only_lists_and_layouts_are_strict() -> None:
    calls: list[dict[str, Any]] = []

    class Fake:
        def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {"Contents": [_obj(_fx(FP1) + "fx_rate.csv")]}

    orphans: list[Any] = []
    report = scan_bucket(Fake(), NORM, NORMALIZED_LAYOUT, orphans.append)  # type: ignore[arg-type]
    assert calls == [{"Bucket": NORM}]
    assert report.orphans == 1 and len(orphans) == 1
    assert RAW_LAYOUT.fullmatch("trm_soda/extraction_date=2026-10-01/batch_id=bad/x") is None


def test_escaping_keeps_each_record_on_one_line(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    weird = "a\nb\x01\u00e9\\\u2028c"
    with Stubber(client) as stubber:
        _list(
            stubber,
            RAW,
            [
                _obj(_raw(B2) + "pay\nload.csv", 7),  # orphan group whose key holds a newline
                _obj("stray/" + weird),
            ],
        )
        _list(stubber, NORM, [])
        result = _run(monkeypatch, stubber, client)
    assert result.exit_code == 0
    escaped = r"stray/a\nb\x01\xe9\\\u2028c"
    assert result.stdout.split("\n") == [
        f"orphan bucket=pits-raw prefix={_raw(B2)} objects=1 bytes=7 "
        "newest=2026-10-01T12:00:00+00:00",
        f"unexpected bucket=pits-raw key={escaped}",
        "bucket=pits-raw groups=1 committed=0 orphans=1 orphan_bytes=7 unexpected=1",
        "bucket=pits-normalized groups=0 committed=0 orphans=0 orphan_bytes=0 unexpected=0",
        "",
    ]


def test_no_such_bucket_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    with Stubber(client) as stubber:
        stubber.add_client_error("list_objects_v2", "NoSuchBucket", http_status_code=404)
        result = _run(monkeypatch, stubber, client)
    assert result.exit_code == 1
    assert "NoSuchBucket" in result.stderr


def test_truncated_without_token_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    with Stubber(client) as stubber:
        stubber.add_response(
            "list_objects_v2",
            {"Contents": [_obj(_raw(B1) + "manifest.json")], "IsTruncated": True},
            {"Bucket": RAW},
        )
        result = _run(monkeypatch, stubber, client)
    assert result.exit_code == 1
    assert "NextContinuationToken" in result.stderr


def test_truncated_without_token_raises_orphans_error() -> None:
    class Fake:
        def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]:
            return {"Contents": [], "IsTruncated": True}

    with pytest.raises(OrphansError):
        scan_bucket(Fake(), RAW, RAW_LAYOUT, lambda orphan: None)  # type: ignore[arg-type]


def test_format_timestamp_naive_is_utc() -> None:
    assert format_timestamp(datetime(2026, 10, 1, 12, 0)) == "2026-10-01T12:00:00+00:00"

"""Offline tests for `pits extract trm`.

The S3 side is replaced through the `store_factory` seam (a shared MemoryRawStore) and the SODA
side through `soda_factory` (a real SodaClient over httpx.MockTransport), so the whole command
runs end to end without network, and Typer exit codes/messages are the real ones.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from botocore.exceptions import InvalidRegionError
from typer.testing import CliRunner

from pits.cli import app
from pits.ingestion.manifest import Manifest
from pits.ingestion.raw_store import MemoryRawStore
from pits.sources import cli as extract_cli
from pits.sources.soda.client import SodaClient
from pits.sources.soda.settings import SodaSettings
from pits.storage.client import build_s3_client

runner = CliRunner()

TOKEN = "soda-test-token-value-xyz"
S3_SECRET = "cli-extract-s3-secret-xyz-0123456789"
ENV = {
    "S3_ENDPOINT_URL": "http://127.0.0.1:9",
    "PITS_S3_WRITER_ACCESS_KEY_ID": "WRITERKEYEXAMPLE0001",
    "PITS_S3_WRITER_SECRET_ACCESS_KEY": S3_SECRET,
    "S3_RAW_BUCKET": "pits-raw",
}
COLUMNS = [
    {"fieldName": "valor", "dataTypeName": "number"},
    {"fieldName": "unidad", "dataTypeName": "text"},
    {"fieldName": "vigenciadesde", "dataTypeName": "calendar_date"},
    {"fieldName": "vigenciahasta", "dataTypeName": "calendar_date"},
]
START = date(2026, 1, 1)
BATCH_1 = "0b6f6c1e-3c1a-4f0e-9a51-2d4c6f8e9a10"
BATCH_2 = "1c7a7d2f-4d2b-4a1f-8b62-3e5d7a9fab21"


def make_rows(n: int) -> list[dict]:
    rows = []
    for i in range(n):
        stamp = f"{(START + timedelta(days=i)).isoformat()}T00:00:00.000"
        rows.append(
            {"valor": "3900.5", "unidad": "COP", "vigenciadesde": stamp, "vigenciahasta": stamp}
        )
    return rows


class Env:
    """Mutable fake world: dataset rows, HTTP failure mode, shared store, batch ids."""

    def __init__(self) -> None:
        self.rows = make_rows(4)
        self.status: int | None = None
        self.store = MemoryRawStore()
        self.batch_ids = [BATCH_1, BATCH_2]
        self.tokens_seen: list[str | None] = []
        self.count_override: str | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.tokens_seen.append(request.headers.get("X-App-Token"))
        if request.url.path.startswith("/api/views/"):
            return httpx.Response(200, json={"rowsUpdatedAt": 7, "columns": COLUMNS})
        if self.status:
            return httpx.Response(self.status)
        params = request.url.params
        rows = self.rows
        match = re.fullmatch(
            r"vigenciadesde (>=?) '(\d{4}-\d{2}-\d{2})T.*'", params.get("$where", "")
        )
        if match:
            op, day = match.groups()
            rows = [
                r
                for r in rows
                if (r["vigenciadesde"][:10] >= day if op == ">=" else r["vigenciadesde"][:10] > day)
            ]
        if params.get("$select") == "count(*)":
            count = str(len(rows)) if self.count_override is None else self.count_override
            return httpx.Response(200, json=[{"count": count}])
        offset, limit = int(params["$offset"]), int(params["$limit"])
        return httpx.Response(200, content=json.dumps(rows[offset : offset + limit]).encode())


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Env:
    env = Env()
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("SODA_APP_TOKEN", TOKEN)
    monkeypatch.delenv("SODA_BASE_URL", raising=False)
    monkeypatch.delenv("S3_NORMALIZED_BUCKET", raising=False)
    monkeypatch.setattr(extract_cli, "client_factory", lambda settings: object())
    monkeypatch.setattr(extract_cli, "store_factory", lambda client, bucket: env.store)
    monkeypatch.setattr(
        extract_cli,
        "soda_factory",
        lambda settings: SodaClient(
            SodaSettings(base_url="https://example.test", app_token=settings.app_token),
            transport=httpx.MockTransport(env.handler),
            sleep=lambda s: None,
            jitter=lambda: 0.0,
        ),
    )
    monkeypatch.setattr(extract_cli, "clock", lambda: datetime(2026, 10, 10, 12, tzinfo=UTC))
    monkeypatch.setattr(extract_cli, "batch_id_factory", lambda: env.batch_ids.pop(0))
    return env


def manifest_key(batch_id: str) -> str:
    return f"superfinanciera_trm/extraction_date=2026-10-10/batch_id={batch_id}/manifest.json"


def test_first_run_is_a_full_backfill_with_exact_output(world: Env) -> None:
    result = runner.invoke(app, ["extract", "trm"])
    assert result.exit_code == 0, result.stderr
    assert result.stdout == (
        f"batch_id={BATCH_1} mode=full rows=4 files=1 watermark_from=none "
        f"watermark_to=2026-01-04 manifest=s3://pits-raw/{manifest_key(BATCH_1)}\n"
    )
    assert result.stderr == ""
    manifest = Manifest.from_json(world.store.get(manifest_key(BATCH_1)))
    assert manifest.app_token_used is True
    assert TOKEN in world.tokens_seen  # sent as header only
    assert all(TOKEN.encode() not in body for body in world.store.objects.values())


def test_explicit_full_flag(world: Env) -> None:
    result = runner.invoke(app, ["extract", "trm", "--full"])
    assert result.exit_code == 0 and "mode=full" in result.stdout


def test_second_run_is_incremental(world: Env) -> None:
    assert runner.invoke(app, ["extract", "trm"]).exit_code == 0
    world.rows = make_rows(6)
    result = runner.invoke(app, ["extract", "trm"])
    assert result.exit_code == 0, result.stderr
    assert result.stdout == (
        f"batch_id={BATCH_2} mode=incremental rows=2 files=1 watermark_from=2026-01-04 "
        f"watermark_to=2026-01-06 manifest=s3://pits-raw/{manifest_key(BATCH_2)}\n"
    )


def test_incremental_without_news_commits_empty_batch(world: Env) -> None:
    runner.invoke(app, ["extract", "trm"])
    result = runner.invoke(app, ["extract", "trm"])
    assert result.exit_code == 0
    assert "rows=0 files=0 watermark_from=2026-01-04 watermark_to=2026-01-04" in result.stdout


@pytest.mark.parametrize("value", ["pits-raw", "Bad_Name", "pits-contract-abcd1234"])
def test_invalid_normalized_bucket_fails_extract_fast(
    world: Env, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    # Chosen behavior: storage config is shared, so a bad S3_NORMALIZED_BUCKET fails fast (D74).
    monkeypatch.setenv("S3_NORMALIZED_BUCKET", value)
    result = runner.invoke(app, ["extract", "trm"])
    assert result.exit_code == 1
    assert result.stdout == "" and "S3_NORMALIZED_BUCKET" in result.stderr
    assert world.store.objects == {}


def test_since_reloads_from_date(world: Env) -> None:
    runner.invoke(app, ["extract", "trm"])
    result = runner.invoke(app, ["extract", "trm", "--since", "2026-01-03"])
    assert result.exit_code == 0, result.stderr
    assert "mode=since rows=2 files=1 watermark_from=2026-01-02 watermark_to=2026-01-04" in (
        result.stdout
    )


def test_full_and_since_are_mutually_exclusive(world: Env) -> None:
    result = runner.invoke(app, ["extract", "trm", "--full", "--since", "2026-01-03"])
    assert result.exit_code == 2
    assert result.stderr.startswith("error: ") and "mutually exclusive" in result.stderr
    assert world.store.objects == {}


@pytest.mark.parametrize("value", ["2026-1-3", "20260103", "03/01/2026", "2026-02-30", "x"])
def test_since_must_be_a_strict_iso_date(world: Env, value: str) -> None:
    result = runner.invoke(app, ["extract", "trm", "--since", value])
    assert result.exit_code == 2
    assert result.stderr.startswith("error: ") and "YYYY-MM-DD" in result.stderr
    assert world.store.objects == {}


def test_since_gap_is_usage_error(world: Env) -> None:
    runner.invoke(app, ["extract", "trm"])
    before = set(world.store.objects)
    result = runner.invoke(app, ["extract", "trm", "--since", "2026-01-09"])
    assert result.exit_code == 2
    assert result.stderr.startswith("error: ") and "leave a gap" in result.stderr
    assert result.stdout == ""
    assert set(world.store.objects) == before


def test_since_gap_without_previous_batch_is_usage_error(world: Env) -> None:
    result = runner.invoke(app, ["extract", "trm", "--since", "2027-01-01"])
    assert result.exit_code == 2 and "leave a gap" in result.stderr
    assert world.store.objects == {}


def test_transient_error_exits_3(world: Env) -> None:
    world.status = 503
    result = runner.invoke(app, ["extract", "trm"])
    assert result.exit_code == 3
    assert result.stderr.startswith("error: ") and "503" in result.stderr
    assert result.stdout == "" and "Traceback" not in result.stderr


def test_truncated_extraction_exits_3_without_manifest(world: Env) -> None:
    world.count_override = "9"  # the source announces more rows than it serves
    result = runner.invoke(app, ["extract", "trm"])
    assert result.exit_code == 3
    assert result.stderr.startswith("error: ") and "Truncated extraction" in result.stderr
    assert result.stdout == ""
    assert not any(k.endswith("manifest.json") for k in world.store.objects)


def test_malformed_count_exits_1(world: Env) -> None:
    world.count_override = "many"
    result = runner.invoke(app, ["extract", "trm"])
    assert result.exit_code == 1 and "Count" in result.stderr
    assert result.stdout == "" and world.store.objects == {}


def test_token_with_http_base_url_exits_1_without_printing_the_token(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SODA_BASE_URL", "http://soda.example")
    result = runner.invoke(app, ["extract", "trm"])
    assert result.exit_code == 1 and "https" in result.stderr
    assert TOKEN not in result.stdout + result.stderr
    assert world.store.objects == {}


def test_permanent_error_exits_1(world: Env) -> None:
    world.status = 404
    result = runner.invoke(app, ["extract", "trm"])
    assert result.exit_code == 1
    assert result.stderr.startswith("error: ") and "404" in result.stderr
    assert result.stdout == "" and "Traceback" not in result.stderr


def test_missing_variables_exit_1_naming_the_variable(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("S3_RAW_BUCKET")
    result = runner.invoke(app, ["extract", "trm"])
    assert result.exit_code == 1
    assert result.stderr.startswith("error: ") and "S3_RAW_BUCKET" in result.stderr


def test_invalid_soda_base_url_exits_1(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SODA_BASE_URL", "ftp://nope")
    result = runner.invoke(app, ["extract", "trm"])
    assert result.exit_code == 1 and "SODA_BASE_URL" in result.stderr


def test_secrets_never_printed_on_any_path(world: Env) -> None:
    outputs = []
    for status in (None, 503, 404):
        world.status = status
        world.batch_ids = [BATCH_1, BATCH_2, BATCH_1]
        world.store = MemoryRawStore()
        result = runner.invoke(app, ["extract", "trm"])
        outputs.append(result.stdout + result.stderr)
    assert all(TOKEN not in out and S3_SECRET not in out for out in outputs)


def test_programming_errors_are_not_swallowed(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(settings):
        raise TypeError("bug")

    monkeypatch.setattr(extract_cli, "soda_factory", boom)
    result = runner.invoke(app, ["extract", "trm"])
    assert result.exit_code != 0
    assert isinstance(result.exception, TypeError)


def test_help_lists_trm_and_other_commands_are_intact(world: Env) -> None:
    assert "trm" in runner.invoke(app, ["extract", "--help"]).stdout
    assert "extract" in runner.invoke(app, ["--help"]).stdout
    version = runner.invoke(app, ["version"])
    assert version.exit_code == 0 and version.stdout.strip()
    assert "init" in runner.invoke(app, ["storage", "--help"]).stdout


def test_since_backfill_start_with_empty_dataset_has_no_watermark(world: Env) -> None:
    world.rows = []
    result = runner.invoke(app, ["extract", "trm", "--since", "1991-12-02"])
    assert result.exit_code == 0, result.stderr
    assert "rows=0 files=0 watermark_from=1991-12-01 watermark_to=none" in result.stdout


def test_storage_client_construction_error_exits_1(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    def bad_client(settings):
        raise InvalidRegionError(region_name="x")

    monkeypatch.setattr(extract_cli, "client_factory", bad_client)
    result = runner.invoke(app, ["extract", "trm"])
    assert result.exit_code == 1
    assert result.stderr.startswith("error: storage client error (InvalidRegionError)")
    assert "Traceback" not in result.stderr and result.stdout == ""


def test_secrets_not_leaked_with_real_s3_client_and_invalid_region(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("S3_REGION", "not a region!")
    monkeypatch.setattr(extract_cli, "client_factory", build_s3_client)
    result = runner.invoke(app, ["extract", "trm"])
    assert result.exit_code == 1
    for secret in (S3_SECRET, TOKEN):
        assert secret not in result.stdout and secret not in result.stderr


# --- pits extract runt -------------------------------------------------------------------------

RUNT_COLUMNS = [
    {"fieldName": name, "dataTypeName": kind}
    for name, kind in (
        ("nombre_departamento", "text"),
        ("nombre_municipio", "text"),
        ("nombre_servicio", "text"),
        ("estado_del_vehiculo", "text"),
        ("nombre_de_la_clase", "text"),
        ("fecha_de_registro", "number"),
        ("cantidad", "number"),
        ("mes_de_publicacion", "text"),
        ("a_o_de_publicacion", "number"),
    )
]
RUNT_PREFIX = "mintransporte_runt_parque/extraction_date=2026-10-10"


def runt_row(i: int) -> dict[str, str]:
    return {
        "nombre_departamento": "ANTIOQUIA",
        "nombre_municipio": f"MUNI{i}",
        "nombre_servicio": "PARTICULAR",
        "estado_del_vehiculo": "ACTIVO",
        "nombre_de_la_clase": "CAMPERO",
        "fecha_de_registro": "1999",
        "cantidad": "2",
        "mes_de_publicacion": "OCTUBRE",
        "a_o_de_publicacion": "2026",
    }


class RuntEnv(Env):
    def __init__(self) -> None:
        super().__init__()
        self.runt_rows = [runt_row(i) for i in range(4)]
        self.updated_at = 7
        self.columns = RUNT_COLUMNS

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.tokens_seen.append(request.headers.get("X-App-Token"))
        if request.url.path.startswith("/api/views/"):
            return httpx.Response(
                200, json={"rowsUpdatedAt": self.updated_at, "columns": self.columns}
            )
        if self.status:
            return httpx.Response(self.status)
        params = request.url.params
        if "$group" in params:
            group = {
                "a_o_de_publicacion": "2026",
                "mes_de_publicacion": "OCTUBRE",
                "count": str(len(self.runt_rows)),
            }
            return httpx.Response(200, json=[group])
        offset, limit = int(params["$offset"]), int(params["$limit"])
        return httpx.Response(
            200, content=json.dumps(self.runt_rows[offset : offset + limit]).encode()
        )


@pytest.fixture
def runt_world(monkeypatch: pytest.MonkeyPatch) -> RuntEnv:
    env = RuntEnv()
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("SODA_APP_TOKEN", TOKEN)
    monkeypatch.delenv("SODA_BASE_URL", raising=False)
    monkeypatch.delenv("S3_NORMALIZED_BUCKET", raising=False)
    monkeypatch.setattr(extract_cli, "client_factory", lambda settings: object())
    monkeypatch.setattr(extract_cli, "store_factory", lambda client, bucket: env.store)
    monkeypatch.setattr(
        extract_cli,
        "soda_factory",
        lambda settings: SodaClient(
            SodaSettings(base_url="https://example.test", app_token=settings.app_token),
            transport=httpx.MockTransport(env.handler),
            sleep=lambda s: None,
            jitter=lambda: 0.0,
        ),
    )
    monkeypatch.setattr(extract_cli, "clock", lambda: datetime(2026, 10, 10, 12, tzinfo=UTC))
    monkeypatch.setattr(extract_cli, "batch_id_factory", lambda: env.batch_ids.pop(0))
    return env


def runt_manifest(batch_id: str) -> str:
    return f"{RUNT_PREFIX}/batch_id={batch_id}/manifest.json"


def test_runt_commits_with_exact_output(runt_world: RuntEnv) -> None:
    result = runner.invoke(app, ["extract", "runt"])
    assert result.exit_code == 0, result.stderr
    assert result.stdout == (
        f"outcome=committed batch_id={BATCH_1} publication=2026-10 rows=4 files=1 "
        f"manifest=s3://pits-raw/{runt_manifest(BATCH_1)}\n"
    )
    assert result.stderr == ""
    manifest = Manifest.from_json(runt_world.store.get(runt_manifest(BATCH_1)))
    assert manifest.app_token_used is True and manifest.source_rows_updated_at == 7


def test_runt_second_run_is_unchanged_and_force_creates_batch(runt_world: RuntEnv) -> None:
    assert runner.invoke(app, ["extract", "runt"]).exit_code == 0
    before = set(runt_world.store.objects)
    second = runner.invoke(app, ["extract", "runt"])
    assert second.exit_code == 0, second.stderr
    assert second.stdout == (
        f"outcome=unchanged batch_id={BATCH_1} publication=2026-10 rows=4 files=1 "
        f"manifest=s3://pits-raw/{runt_manifest(BATCH_1)}\n"
    )
    assert set(runt_world.store.objects) == before
    forced = runner.invoke(app, ["extract", "runt", "--force"])
    assert forced.exit_code == 0, forced.stderr
    assert forced.stdout.startswith(f"outcome=committed batch_id={BATCH_2} ")


def test_runt_schema_drift_exit_1(runt_world: RuntEnv) -> None:
    runt_world.columns = RUNT_COLUMNS[:-1]
    result = runner.invoke(app, ["extract", "runt"])
    assert result.exit_code == 1
    assert result.stdout == "" and result.stderr.startswith("error: ")
    assert runt_world.store.objects == {}
    assert TOKEN not in result.stdout + result.stderr


def test_runt_truncation_exit_3(runt_world: RuntEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    original = runt_world.handler

    def short(request: httpx.Request) -> httpx.Response:
        response = original(request)
        if "$group" in request.url.params:
            return httpx.Response(200, json=[{**response.json()[0], "count": "9"}])
        return response

    monkeypatch.setattr(runt_world, "handler", short)
    result = runner.invoke(app, ["extract", "runt"])
    assert result.exit_code == 3
    assert result.stderr.startswith("error: ") and "Truncated" in result.stderr
    assert TOKEN not in result.stdout + result.stderr


def test_runt_http_503_exit_3(runt_world: RuntEnv) -> None:
    runt_world.status = 503
    result = runner.invoke(app, ["extract", "runt"])
    assert result.exit_code == 3 and result.stdout == ""
    assert TOKEN not in result.stdout + result.stderr


def test_runt_invalid_storage_config_exit_1(
    runt_world: RuntEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("S3_RAW_BUCKET", raising=False)
    monkeypatch.setenv("S3_NORMALIZED_BUCKET", "pits-raw")
    result = runner.invoke(app, ["extract", "runt"])
    assert result.exit_code == 1 and result.stdout == ""


@pytest.mark.parametrize("command", ["trm", "runt"])
def test_extract_does_not_fall_back_to_admin(
    world: Env, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    for name in ("PITS_S3_WRITER_ACCESS_KEY_ID", "PITS_S3_WRITER_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name)
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "ADMINKEYEXAMPLE0001")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", S3_SECRET)
    result = runner.invoke(app, ["extract", command])
    assert result.exit_code == 1 and result.stdout == ""
    assert "PITS_S3_WRITER_ACCESS_KEY_ID" in result.stderr
    assert S3_SECRET not in result.stdout + result.stderr

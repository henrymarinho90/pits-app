"""CI/compose parity guard (D112): the CI `pg` job must run the same Postgres as compose.

Offline. Values are read with PyYAML (already in uv.lock, transitive of dbt; no new dependency).
- compose (docker-compose.yml): `services.postgres.image` (tag + digest) and
  `services.postgres.environment.POSTGRES_INITDB_ARGS`.
- CI (.github/workflows/ci.yml, D112): the job `pg` starts Postgres with `docker run` in a step (a
  service container would start before the job's generated credentials exist). Contract for S2:
  job-level `env: {PG_IMAGE, PG_INITDB_ARGS}` read from `jobs.pg.env`, and a step whose `run` has
  `docker run`, `-e POSTGRES_INITDB_ARGS="$PG_INITDB_ARGS"` and `"$PG_IMAGE"`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"
CI = ROOT / ".github" / "workflows" / "ci.yml"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _compose_values() -> tuple[str, str]:
    pg = _load(COMPOSE)["services"]["postgres"]
    return pg["image"], pg["environment"]["POSTGRES_INITDB_ARGS"]


def _ci_pg_job() -> dict:
    return _load(CI)["jobs"]["pg"]


def _ci_values() -> tuple[str, str]:
    env = _ci_pg_job()["env"]
    return env["PG_IMAGE"], env["PG_INITDB_ARGS"]


def test_compose_postgres_is_pinned_with_digest_and_initdb_args():
    image, args = _compose_values()
    assert "@sha256:" in image
    assert "--locale-provider=builtin" in args


def test_ci_pg_job_matches_compose_postgres():
    assert _ci_values() == _compose_values()


def test_ci_pg_job_docker_run_uses_env_vars():
    runs = [step.get("run", "") for step in _ci_pg_job()["steps"]]
    assert any(
        "docker run" in r
        and '-e POSTGRES_INITDB_ARGS="$PG_INITDB_ARGS"' in r
        and '"$PG_IMAGE"' in r
        for r in runs
    ), 'no step runs `docker run` with -e POSTGRES_INITDB_ARGS="$PG_INITDB_ARGS" and "$PG_IMAGE"'


def _run_text() -> str:
    return next(s["run"] for s in _ci_pg_job()["steps"] if "docker run" in s.get("run", ""))


def test_ci_docker_run_resources_and_port_match_compose():
    pg = _load(COMPOSE)["services"]["postgres"]
    run = _run_text()
    assert pg["mem_limit"] == "1g" and pg["memswap_limit"] == "1g"
    assert f"--memory {pg['mem_limit']}" in run
    assert f"--memory-swap {pg['memswap_limit']}" in run
    assert f"--shm-size {pg['shm_size']}" in run
    # compose: "127.0.0.1:${POSTGRES_HOST_PORT:-5433}:5432"; CI pins 5433 (the default).
    port = pg["ports"][0].replace("${POSTGRES_HOST_PORT:-5433}", "5433")
    assert f"-p {port}" in run


def test_upload_step_blanks_the_generated_passwords():
    step = next(s for s in _ci_pg_job()["steps"] if s.get("name") == "Upload junit")
    names = {
        "POSTGRES_PASSWORD",
        "PITS_PG_LOADER_PASSWORD",
        "PITS_PG_READER_PASSWORD",
        "PITS_PG_TRANSFORMER_PASSWORD",
    }
    assert {k: step["env"].get(k) for k in names} == dict.fromkeys(names, "")

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

import pytest
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


@pytest.mark.xfail(
    strict=True,
    raises=KeyError,
    reason="CI job `pg` does not exist yet (arrives in S2 of Fase 5, D112); remove then",
)
def test_ci_pg_job_matches_compose_postgres():
    assert _ci_values() == _compose_values()


@pytest.mark.xfail(
    strict=True,
    raises=KeyError,
    reason="CI job `pg` does not exist yet (arrives in S2 of Fase 5, D112); remove then",
)
def test_ci_pg_job_docker_run_uses_env_vars():
    runs = [step.get("run", "") for step in _ci_pg_job()["steps"]]
    assert any(
        "docker run" in r
        and '-e POSTGRES_INITDB_ARGS="$PG_INITDB_ARGS"' in r
        and '"$PG_IMAGE"' in r
        for r in runs
    ), 'no step runs `docker run` with -e POSTGRES_INITDB_ARGS="$PG_INITDB_ARGS" and "$PG_IMAGE"'

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

import re
import tomllib
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


def _ci_contract_job() -> dict:
    return _load(CI)["jobs"]["contract"]


def _contract_runs() -> str:
    return "\n".join(s.get("run", "") for s in _ci_contract_job()["steps"])


def test_network_contract_image_matches_compose_seaweedfs():
    # The D119 probe runs a throwaway container of the compose image; the pins must not drift.
    src = (ROOT / "tests" / "contract" / "test_seaweedfs_network_contract.py").read_text(
        encoding="utf-8"
    )
    image = _load(COMPOSE)["services"]["seaweedfs"]["image"]
    assert f'"{image}"' in src


def test_ci_contract_job_uses_compose_and_default_probe_network():
    runs = _contract_runs()
    assert "uv run pits storage init" in runs
    assert "docker compose up -d --wait seaweedfs postgres" in runs
    # Each contract/pg test runs in exactly one job: contract takes all `contract` (incl.
    # contract+pg e2e); pg takes the rest of `pg`.
    assert "pytest -m contract -q" in runs
    pg_runs = "\n".join(s.get("run", "") for s in _ci_pg_job()["steps"])
    assert 'pytest -m "pg and not contract"' in pg_runs
    assert "docker compose down -v" in runs
    # compose `name: pits` -> network pits_default, the probe default (no override needed).
    assert _load(COMPOSE)["name"] == "pits"


def test_ci_contract_job_never_uses_env_file_and_blanks_secrets_on_upload():
    job = _ci_contract_job()
    assert any(s.get("run") == "test ! -e .env" for s in job["steps"])
    step = next(s for s in job["steps"] if s.get("name") == "Upload junit")
    assert step["if"] == "always()"
    # Names come from the generator step itself (dict entries built with `secrets.*`), not a
    # hand-written list: a new generated secret that the upload step forgets to blank fails here.
    generator = _step(job, "Generate ephemeral credentials")["run"]
    secrets_ = set(re.findall(r'"([A-Z][A-Z0-9_]+)":\s*secrets\.', generator))
    assert len(secrets_) >= 11, secrets_
    assert {k: step["env"].get(k) for k in secrets_} == dict.fromkeys(secrets_, "")


def _step(job: dict, name: str) -> dict:
    return next(s for s in job["steps"] if s.get("name") == name)


def test_ci_contract_job_always_tears_down_compose():
    assert _step(_ci_contract_job(), "Compose down")["if"] == "always()"


def test_ci_jobs_mask_generated_credentials():
    for job in (_ci_pg_job(), _ci_contract_job()):
        assert "::add-mask::" in _step(job, "Generate ephemeral credentials")["run"]


def test_default_pytest_run_excludes_exactly_the_job_scoped_markers():
    # The partition contract/pg/airflow depends on addopts excluding them from the plain run and on
    # the `ci` job not overriding it with `-m`.
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"][
        "ini_options"
    ]
    assert "-m 'not contract and not pg and not airflow'" in cfg["addopts"]
    declared = {m.split(":", 1)[0].strip() for m in cfg["markers"]}
    assert declared == {"contract", "pg", "airflow"}
    tests_step = _step(_load(CI)["jobs"]["ci"], "Tests")
    assert tests_step["run"].strip() == "uv run pytest -q"

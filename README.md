# Pits App — Plataforma de datos

Portafolio de Data Engineering para un marketplace de repuestos de autos y motos. Alcance (D68–D73): plataforma de datos (lo implementado hoy), marketplace web de autopartes Colombia + EE. UU. y app de gestión de talleres pequeños en Colombia con facturación electrónica; los productos avanzan por hitos aprobados y aún no tienen código. Ver `docs/01_project_brief.md`.

## Requisitos

- [uv](https://docs.astral.sh/uv/) (instala Python 3.12 desde `.python-version`).

## Setup

```bash
uv sync
```

CI usa `uv sync --locked`. Si cambias `pyproject.toml`, corre `uv lock` y commitea `uv.lock`; si no, CI falla (intencional).

## Comandos

```bash
uv run pits --help
uv run pits version
uv run ruff check .
uv run ruff format .
uv run ruff format --check .   # lo que corre CI
uv run pytest -q
```

## Stack local (perfil core)

SeaweedFS (S3, D57/D63) + Postgres (D60) en `docker-compose.yml`, solo en `127.0.0.1`.

```bash
cp -n .env.example .env                           # no sobrescribe un .env existente; reemplaza las credenciales change-me
docker compose up -d                              # COMPOSE_PROFILES=core viene en .env
uv run --env-file .env pits storage init          # crea/verifica el bucket raw pits-raw (D61), idempotente
uv run --env-file .env pits extract trm           # TRM (datos.gov.co 32sa-8pi3) → pits-raw; incremental (D66); --full | --since YYYY-MM-DD
uv run pytest -q                                  # tests offline (lo que corre CI)
uv run --env-file .env pytest -m contract -q      # tests de contrato contra el S3 local (D58)
uv run --env-file .env pits db migrate            # roles, base pits_warehouse y migraciones (D79/D80), idempotente
uv run --env-file .env pits load fx-rate          # último fx_rate normalizado → landing.fx_rate (D82); --fingerprint SHA | --repair
uv run --env-file .env pits transform build        # dbt: staging.stg_fx_rate + marts.fct_fx_rate_daily y sus tests (D87/D88)
uv run --env-file .env pits transform freshness    # frescura de la última carga de fx_rate (aviso 2 días, error 7)
uv run pits transform parse                       # valida el proyecto dbt sin conectarse (lo que corre CI)
uv run --env-file .env pytest -m pg -q            # tests contra el Postgres local en bases pits_test_* (D84)
scripts/measure_storage_memory.sh                 # memoria de SeaweedFS (D63) o de otro contenedor (C=, CMD=): bash/Git Bash, stack arriba; reinicia el contenedor
docker compose down                               # sin -v conserva los volúmenes
```

- Postgres se publica en `127.0.0.1:5433` (`POSTGRES_HOST_PORT`): 5432 suele estar ocupado por un Postgres nativo de Windows.
- `docker-compose.spike.yml` (spike de SeaweedFS) usa el mismo puerto 8333: no lo levantes a la vez que el core.
- `pits db migrate` necesita `PITS_PG_LOADER_PASSWORD`, `PITS_PG_READER_PASSWORD` y `PITS_PG_TRANSFORMER_PASSWORD` (≥16 caracteres; usa valores distintos, el código no lo valida) en `.env`; `pits load` usa solo la del loader y `pits transform build|freshness` solo la del transformer. Mismos exit codes 0/1/2/3. Runbook en `docs/06_status.md`.
- `pits extract trm` escribe páginas `payload-NNNNN.json` y un `manifest.json` al final (D65). Exit codes: 0 batch confirmado, 1 error permanente, 2 uso, 3 transitorio (reintentable). `SODA_APP_TOKEN` es opcional (reduce el throttling de datos.gov.co).

## Orquestación (Fase 4, perfil `orchestration`)

Airflow 3.3.2 con LocalExecutor (D89, D95) sobre el stack core. DAG `trm_daily`: extract → normalize → load → build → freshness, a las 10:00 America/Bogotá (15:00 UTC), sin catchup (D92). Detalle y runbook en `docs/06_status.md` §3.

```bash
docker compose -f docker-compose.yml --profile core up -d   # 1. core (Postgres) arriba; init-airflow-meta lo necesita
uv run --env-file .env pits db init-airflow-meta            # 2. antes del primer up de orchestration; idempotente, status=created|unchanged (D93)
docker compose -f docker-compose.yml -f docker-compose.orchestration.yml --profile core --profile orchestration up -d   # 3. orchestration
docker compose -f docker-compose.yml -f docker-compose.orchestration.yml --profile core --profile orchestration down   # sin -v conserva los volúmenes
```

- En un worktree no hay `.env`: usa `--env-file ../pits-app/.env` tanto en `uv run` como en `docker compose` (p. ej. `docker compose --env-file ../pits-app/.env -f docker-compose.yml -f docker-compose.orchestration.yml ...`).

- En PowerShell puedes fijar `COMPOSE_FILE` con `docker-compose.yml;docker-compose.orchestration.yml` (separador `;` en Windows, `:` en Linux; el de Linux no se probó).
- UI: `http://127.0.0.1:8080` (solo loopback), usuario `admin`, contraseña `AIRFLOW_ADMIN_PASSWORD` de `.env`.
- Disparo manual: en la UI, "Trigger DAG" con conf JSON, por ejemplo `{"extract_mode": "since", "since": "2026-10-01"}` o `{"extract_mode": "full"}`. `--repair` y `--fingerprint` solo por CLI manual (D92).
- Al des-pausar un DAG, Airflow crea la corrida del último punto cron ya pasado.
- Cambiar un DAG exige `docker build` y recrear los contenedores.
- Tests offline de orchestration: en CI (Linux) con `uv run --locked --project orchestration pytest orchestration/tests -q`; en Windows no colectan (Airflow no soporta Windows; el host falla con `ImportError: cannot import name 'ObjectStoragePath' from 'airflow.sdk'`) y se corren dentro de la imagen (D94). Comando verificado por el revisor en Windows (83 passed; necesita red):

```bash
MSYS_NO_PATHCONV=1 docker run --rm --entrypoint bash -v "$(pwd -W):/repo:ro" -w /repo/orchestration pits-airflow:dev -c 'pip install --quiet --no-cache-dir --target /tmp/pt pytest==9.1.1 iniconfig==2.3.1 && PYTHONPATH=/tmp/pt python -m pytest tests -q -p no:cacheprovider'
```
- Integración (`-m airflow`, excluida por defecto): `MSYS_NO_PATHCONV=1 uv run --env-file .env pytest -m airflow -q`, desde Git Bash, con el stack arriba, lejos de las 15:00 UTC y sin corridas activas. Tarda unos 23 minutos.
- Limpiar tareas: `airflow tasks clear` sin `-s` y `-e` limpia todas las corridas; usa `-s`/`-e` con `-t load` (`-t '^load$'` no limpia nada).

## Estructura

- `src/pits/` — paquete y CLI (Typer); `src/pits/storage/` — settings, cliente S3 y bucket raw.
- `src/pits/sources/` — fuentes: cliente SODA (`soda/`) y extractor TRM (`trm/`); `src/pits/ingestion/` — raw store write-once y manifest.
- `src/pits/normalized/` — artefactos normalizados (`fx_rate`) y lector verificado; `src/pits/warehouse/` — conexión, bootstrap, migraciones SQL y loader a Postgres; `src/pits/transform/` — wrapper de dbt.
- `transform/` — proyecto dbt `pits_transform` (D85): modelos `staging` y `marts`, tests y freshness.
- `orchestration/` — DAGs de Airflow (`dags/trm_daily.py`, operador `dags/pits_cli/`) y su proyecto uv con los constraints de Airflow (D94); `docker/airflow/` — Dockerfile e imagen `pits-airflow` (D89); `docker-compose.orchestration.yml` — servicios de Airflow (D95).
- `tests/` — tests con pytest; `tests/contract/` — tests de contrato (marker `contract`); `tests/pg/` — tests contra Postgres (marker `pg`); ambos excluidos por defecto.
- `scripts/` — scripts operativos.
- `docs/` — documentación del proyecto:
  - `05_decisions_log.md` — decisiones (D<n>).
  - `06_status.md` — estado actual y siguiente paso.
- `.github/workflows/ci.yml` — CI mínimo (D49).

## Estado

Fase 3: loader `fx_rate` a Postgres (D78–D84) y transformación dbt `stg_fx_rate` → `fct_fx_rate_daily` (D85–D88). Fase 4: orquestación con Airflow del pipeline TRM (D89–D95), implementada en `feat/airflow-trm`; pendiente de revisión final, PR, CI y merge. Ver `docs/06_status.md`.

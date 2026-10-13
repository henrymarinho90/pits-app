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
uv run --env-file .env pits storage init          # crea/verifica el bucket raw pits-raw (D61) y aplica la policy write-once (policy=applied), idempotente; usa el admin S3_*
uv run --env-file .env pits storage orphans       # inventario de solo lectura de huérfanos en el almacenamiento (identidad reader)
uv run --env-file .env pits extract trm           # TRM (datos.gov.co 32sa-8pi3) → pits-raw; incremental (D66); --full | --since YYYY-MM-DD
uv run pytest -q                                  # tests offline (lo que corre CI)
uv run --env-file .env pytest -m contract -q      # tests de contrato contra el S3 local (D58)
uv run --env-file .env pits db migrate            # roles, base pits_warehouse y migraciones (D79/D80), idempotente
uv run --env-file .env pits load fx-rate          # último fx_rate normalizado → landing.fx_rate (D82); --fingerprint SHA | --repair
uv run --env-file .env pits extract runt           # RUNT parque automotor → pits-raw; si la fuente no cambió da `unchanged`; --force crea un batch nuevo de ~50 MB que no se borra nunca
uv run --env-file .env pits normalize runt         # batch raw del RUNT → artefactos normalizados
uv run --env-file .env pits load vehicle-fleet     # → landing.vehicle_fleet_snapshot; --publication YYYY-MM | --fingerprint SHA | --repair
uv run --env-file .env pits transform build        # dbt: staging + marts y sus tests (fx_rate y parque); --select tag:vehicle_fleet | tag:fx_rate (D87/D88)
uv run --env-file .env pits transform freshness    # frescura de las cargas (fx_rate: aviso 2 días, error 7); sin --select evalúa todo, incluido el parque; --select tag:vehicle_fleet | tag:fx_rate
uv run pits transform parse                       # valida el proyecto dbt sin conectarse (lo que corre CI)
uv run --env-file .env pytest -m pg -q            # tests contra el Postgres local en bases pits_test_* (D84)
scripts/measure_storage_memory.sh                 # memoria de SeaweedFS (D63) o de otro contenedor (C=, CMD=): bash/Git Bash, stack arriba; reinicia el contenedor
docker compose down                               # sin -v conserva los volúmenes
```

- Postgres se publica en `127.0.0.1:5433` (`POSTGRES_HOST_PORT`): 5432 suele estar ocupado por un Postgres nativo de Windows.
- `docker-compose.spike.yml` (spike de SeaweedFS) usa el mismo puerto 8333: no lo levantes a la vez que el core.
- `pits db migrate` necesita `PITS_PG_LOADER_PASSWORD`, `PITS_PG_READER_PASSWORD` y `PITS_PG_TRANSFORMER_PASSWORD` (≥16 caracteres; usa valores distintos, el código no lo valida) en `.env`; `pits load` usa solo la del loader y `pits transform build|freshness` solo la del transformer. Mismos exit codes 0/1/2/3. Runbook en `docs/06_status.md`.
- Identidades S3 (D104): `pits extract` y `pits normalize` usan `PITS_S3_WRITER_*`; `pits load` y `pits storage orphans` usan `PITS_S3_READER_*`; `pits storage init` usa el admin `S3_*`. Si falta la variable, el comando sale con exit 1 y nombra la variable. Genera los valores con los comandos de `.env.example`.
- `pits storage init` aplica la policy write-once (`policy=applied`). Quitarla (break-glass) se hace con el admin vía `delete_bucket_policy`, solo con confirmación de Henry.
- Si cambias el JSON de identidades o los nombres de bucket, recrea seaweedfs y vuelve a correr `pits storage init`.
- `pits extract trm` escribe páginas `payload-NNNNN.json` y un `manifest.json` al final (D65). Exit codes: 0 batch confirmado, 1 error permanente, 2 uso, 3 transitorio (reintentable). `SODA_APP_TOKEN` es opcional (reduce el throttling de datos.gov.co).

## Orquestación (Fase 4, perfil `orchestration`)

Airflow 3.3.2 con LocalExecutor (D89, D95) sobre el stack core. Tres DAGs: `trm_daily`, a las 10:00 America/Bogotá (15:00 UTC), y `runt_fleet_snapshot`, a las 11:00 America/Bogotá (16:00 UTC); ambos corren extract → normalize → load → build → freshness, sin catchup (D92). El tercero, `airflow_log_retention`, corre a las 03:00 America/Bogotá y borra los `*.log` de más de 30 días. `runt_fleet_snapshot` acepta el param `force` (solo bool). Detalle y runbook en `docs/06_status.md` §3.

```bash
docker compose -f docker-compose.yml --profile core up -d   # 1. core (Postgres) arriba; init-airflow-meta lo necesita
uv run --env-file .env pits db init-airflow-meta            # 2. antes del primer up de orchestration; idempotente, status=created|unchanged (D93)
docker compose -f docker-compose.yml -f docker-compose.orchestration.yml --profile core --profile orchestration up -d   # 3. orchestration
docker compose -f docker-compose.yml -f docker-compose.orchestration.yml --profile core --profile orchestration down   # sin -v conserva los volúmenes
```

- En un worktree no hay `.env`: usa `--env-file ../pits-app/.env` tanto en `uv run` como en `docker compose` (p. ej. `docker compose --env-file ../pits-app/.env -f docker-compose.yml -f docker-compose.orchestration.yml ...`).

- En PowerShell puedes fijar `COMPOSE_FILE` con `docker-compose.yml;docker-compose.orchestration.yml` (separador `;` en Windows, `:` en Linux; el de Linux no se probó).
- UI: `http://127.0.0.1:8080` (solo loopback), usuario `admin`, contraseña `AIRFLOW_ADMIN_PASSWORD` de `.env`.
- Disparo manual: en la UI, "Trigger DAG" con conf JSON, por ejemplo `{"extract_mode": "since", "since": "2026-10-01"}` o `{"extract_mode": "full"}`. Por CLI: `airflow dags trigger runt_fleet_snapshot -c '{"force": true}'` (si va por `bash -c`, el JSON entre comillas simples). `--repair` y `--fingerprint` solo por CLI manual (D92).
- Al des-pausar un DAG, Airflow crea la corrida del último punto cron ya pasado.
- Cambiar un DAG exige `docker build` y recrear los contenedores.
- Tests offline de orchestration: en CI (Linux) con `uv run --locked --project orchestration pytest orchestration/tests -q`; en Windows no colectan (Airflow no soporta Windows; el host falla con `ImportError: cannot import name 'ObjectStoragePath' from 'airflow.sdk'`) y se corren dentro de la imagen (D94). Comando verificado por el revisor en Windows (137 passed; necesita red):

```bash
MSYS_NO_PATHCONV=1 docker run --rm --entrypoint bash -v "$(pwd -W):/repo:ro" -w /repo/orchestration pits-airflow:dev -c 'pip install --quiet --no-cache-dir --target /tmp/pt pytest==9.1.1 iniconfig==2.3.1 && PYTHONPATH=/tmp/pt python -m pytest tests -q -p no:cacheprovider'
```
- Integración (`-m airflow`, excluida por defecto): `MSYS_NO_PATHCONV=1 uv run --env-file .env pytest -m airflow -q`, desde Git Bash, con el stack arriba, lejos de las 15:00 y 16:00 UTC y sin corridas activas en ninguno de los dos DAGs. Tarda más de 23 min; con RUNT no se ha medido completa (test_3 y test_4 tardan unos 10 min cada uno). Los tests se llaman `test_runt_*` y `test_N_*` (TRM). El caso force solo corre con `PITS_IT_FORCE=1` y cuesta unos 86 MB permanentes en raw y normalized.
- Regla D106: no corras `pits extract` a mano entre 14:45–15:30 ni 15:45–16:30 UTC, ni con corridas activas.
- Limpiar tareas: `airflow tasks clear` sin `-s` y `-e` limpia todas las corridas; usa `-s`/`-e` con `-t load` (`-t '^load$'` no limpia nada).

## Estructura

- `src/pits/` — paquete y CLI (Typer); `src/pits/storage/` — settings, cliente S3 y bucket raw; `src/pits/storage/orphans.py` — inventario de huérfanos (`pits storage orphans`).
- `src/pits/sources/` — fuentes: cliente SODA (`soda/`), extractor TRM (`trm/`) y dominio RUNT (`runt/`: extract, parse, normalize, contract); `src/pits/ingestion/` — raw store write-once y manifest.
- `src/pits/normalized/` — artefactos normalizados (`fx_rate`) y lector verificado, más los módulos `fleet_*` del parque RUNT (`fleet_csv.py`, `fleet_manifest.py`, `fleet_reader.py`); `src/pits/warehouse/` — conexión, bootstrap, migraciones SQL (incl. `0004_landing_vehicle_fleet_snapshot.sql`) y loader a Postgres; `src/pits/transform/` — wrapper de dbt.
- `transform/` — proyecto dbt `pits_transform` (D85): modelos `staging` y `marts` (incl. `stg_vehicle_fleet_snapshot` y `fct_vehicle_fleet_snapshot`), tests y freshness.
- `orchestration/` — DAGs de Airflow (`dags/trm_daily.py`, `dags/runt_fleet_snapshot.py`, `dags/airflow_log_retention.py`, operador `dags/pits_cli/`) y su proyecto uv con los constraints de Airflow (D94); `docker/airflow/` — Dockerfile e imagen `pits-airflow` (D89); `docker-compose.orchestration.yml` — servicios de Airflow (D95).
- `tests/` — tests con pytest; `tests/contract/` — tests de contrato (marker `contract`); `tests/pg/` — tests contra Postgres (marker `pg`); ambos excluidos por defecto.
- `scripts/` — scripts operativos (incl. `scripts/dbt_run_timing.py`).
- `docs/` — documentación del proyecto:
  - `05_decisions_log.md` — decisiones (D<n>).
  - `06_status.md` — estado actual y siguiente paso.
- `.github/workflows/ci.yml` — CI mínimo (D49).

## Estado

Fase 3: loader `fx_rate` a Postgres (D78–D84) y transformación dbt `stg_fx_rate` → `fct_fx_rate_daily` (D85–D88). Fase 4: orquestación con Airflow del pipeline TRM (D89–D95), implementada en `feat/airflow-trm`; pendiente de revisión final, PR, CI y merge. Ver `docs/06_status.md`.

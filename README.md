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

## Estructura

- `src/pits/` — paquete y CLI (Typer); `src/pits/storage/` — settings, cliente S3 y bucket raw.
- `src/pits/sources/` — fuentes: cliente SODA (`soda/`) y extractor TRM (`trm/`); `src/pits/ingestion/` — raw store write-once y manifest.
- `src/pits/normalized/` — artefactos normalizados (`fx_rate`) y lector verificado; `src/pits/warehouse/` — conexión, bootstrap, migraciones SQL y loader a Postgres; `src/pits/transform/` — wrapper de dbt.
- `transform/` — proyecto dbt `pits_transform` (D85): modelos `staging` y `marts`, tests y freshness.
- `tests/` — tests con pytest; `tests/contract/` — tests de contrato (marker `contract`); `tests/pg/` — tests contra Postgres (marker `pg`); ambos excluidos por defecto.
- `scripts/` — scripts operativos.
- `docs/` — documentación del proyecto:
  - `05_decisions_log.md` — decisiones (D<n>).
  - `06_status.md` — estado actual y siguiente paso.
- `.github/workflows/ci.yml` — CI mínimo (D49).

## Estado

Fase 3: loader `fx_rate` a Postgres (D78–D84) y transformación dbt `stg_fx_rate` → `fct_fx_rate_daily` (D85–D88). Ver `docs/06_status.md`.

# Pits App — Plataforma de datos

Portafolio de Data Engineering para un marketplace de repuestos de autos y motos (Colombia/LATAM).

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
scripts/measure_storage_memory.sh                 # memoria de SeaweedFS (D63): bash/Git Bash, stack arriba, ~15 min; reinicia el contenedor
docker compose down                               # sin -v conserva los volúmenes
```

- Postgres se publica en `127.0.0.1:5433` (`POSTGRES_HOST_PORT`): 5432 suele estar ocupado por un Postgres nativo de Windows.
- `docker-compose.spike.yml` (spike de SeaweedFS) usa el mismo puerto 8333: no lo levantes a la vez que el core.
- `pits extract trm` escribe páginas `payload-NNNNN.json` y un `manifest.json` al final (D65). Exit codes: 0 batch confirmado, 1 error permanente, 2 uso, 3 transitorio (reintentable). `SODA_APP_TOKEN` es opcional (reduce el throttling de datos.gov.co).

## Estructura

- `src/pits/` — paquete y CLI (Typer); `src/pits/storage/` — settings, cliente S3 y bucket raw.
- `src/pits/sources/` — fuentes: cliente SODA (`soda/`) y extractor TRM (`trm/`); `src/pits/ingestion/` — raw store write-once y manifest.
- `tests/` — tests con pytest; `tests/contract/` — tests de contrato (marker `contract`, excluidos por defecto).
- `scripts/` — scripts operativos.
- `docs/` — documentación del proyecto:
  - `05_decisions_log.md` — decisiones (D<n>).
  - `06_status.md` — estado actual y siguiente paso.
- `.github/workflows/ci.yml` — CI mínimo (D49).

## Estado

Fase 1, paso 3 (extractor TRM a raw). Ver `docs/06_status.md`.

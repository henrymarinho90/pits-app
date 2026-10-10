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

## Estructura

- `src/pits/` — paquete y CLI (Typer).
- `tests/` — tests con pytest.
- `docs/` — documentación del proyecto:
  - `05_decisions_log.md` — decisiones (D<n>).
  - `06_status.md` — estado actual y siguiente paso.
- `.github/workflows/ci.yml` — CI mínimo (D49).

## Estado

Fase 1, paso 1 (esqueleto). Ver `docs/06_status.md`.

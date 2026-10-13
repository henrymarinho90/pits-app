# Imagen pits-airflow (D89): Airflow 3.3.2 + proyecto pits en un venv aislado.
# Build desde la raiz del repo: docker build -f docker/airflow/Dockerfile -t pits-airflow:dev .

# Base slim 3.3.2 / Python 3.12; digest = indice multi-arch (docker buildx imagetools inspect, 2026-10-12).
FROM apache/airflow:slim-3.3.2-python3.12@sha256:a54e7bd6c4d7a17e55cd14b0ead257877b8f8111680d2692cbdba2ff32bd3ff3

# Drivers de la metadata DB (P3): la slim no trae psycopg2 ni el provider postgres, y Airflow 3.3
# tambien necesita asyncpg (motor async). Solo psycopg2-binary y asyncpg, fijados con hashes
# (--require-hashes, sin red a constraints remotos), en el entorno de Airflow (~/.local) y NO en /opt/pits/.venv, para no mezclar dependencias con dbt.
RUN --mount=type=bind,source=docker/airflow/requirements-airflow.txt,target=/tmp/requirements-airflow.txt \
    pip install --no-cache-dir --require-hashes -r /tmp/requirements-airflow.txt

# Proyecto en /opt/pits como root: src/, .venv, pyproject y uv.lock quedan de solo lectura para
# airflow (y para cualquier UID). Solo transform/ es escribible (dbt crea target/ y logs/).
USER root
WORKDIR /opt/pits

# Capa de dependencias: solo cambia con pyproject.toml / uv.lock / .python-version.
# uv 0.11.26 (version local, digest = indice multi-arch, 2026-10-12) se monta solo durante el RUN,
# no queda en la imagen, y se invoca por ruta absoluta: la base trae otro uv antes en el PATH.
# Venv aislado /opt/pits/.venv sobre el Python del sistema (sin descargar otro); --no-dev quita
# pytest/ruff y el grupo transform (dbt) se mantiene.
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=from=ghcr.io/astral-sh/uv:0.11.26@sha256:3d868e555f8f1dbc324afa005066cd11e1053fc4743b9808ca8025283e65efa5,source=/uv,target=/usr/local/bin/uv \
    UV_PYTHON=/usr/python/bin/python3.12 UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/pits/.venv UV_NO_CACHE=1 UV_COMPILE_BYTECODE=1 \
    /usr/local/bin/uv sync --locked --no-dev --no-install-project

# Codigo: instalacion editable (default de uv sync). pits.transform.runner resuelve el proyecto dbt
# desde su __file__ (/opt/pits/src/pits/... -> /opt/pits/transform) y dbt desde sys.executable
# (/opt/pits/.venv/bin/dbt); una instalacion no editable los resolveria dentro de site-packages.
COPY src/ ./src/
COPY transform/ ./transform/
RUN --mount=from=ghcr.io/astral-sh/uv:0.11.26@sha256:3d868e555f8f1dbc324afa005066cd11e1053fc4743b9808ca8025283e65efa5,source=/uv,target=/usr/local/bin/uv \
    UV_PYTHON=/usr/python/bin/python3.12 UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/pits/.venv UV_NO_CACHE=1 UV_COMPILE_BYTECODE=1 \
    /usr/local/bin/uv sync --locked --no-dev

# transform/ escribible por GID 0 (convencion de la imagen oficial): dbt funciona con cualquier UID
# del grupo root (p. ej. --user 1234:0), no solo con el UID 50000.
# uv deja .venv/.lock con permisos 666: se quita para que nada fuera de transform/ sea escribible.
RUN chgrp -R 0 /opt/pits/transform && chmod -R g+rwX /opt/pits/transform \
    && rm -f /opt/pits/.venv/.lock

# DAGs (S5, D94): ultima capa de codigo para no invalidar la cache de las anteriores al editarlos.
# De root y de solo lectura para airflow (el directorio de la imagen base es del usuario airflow:
# se le quita la propiedad; los procesos de Airflow solo leen). Los tests no entran en la imagen.
COPY --chown=root:root orchestration/dags/ /opt/airflow/dags/
RUN chown root:root /opt/airflow/dags && find /opt/airflow/dags -type d -exec chmod 755 {} + -o -type f -exec chmod 644 {} +

# Vuelve al usuario, WORKDIR y ENTRYPOINT de la imagen oficial.
USER airflow
WORKDIR /opt/airflow

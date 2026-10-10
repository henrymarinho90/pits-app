# 06 — Estado del proyecto

Última actualización: 2026-10-10
Estado: actualizado tras cerrar Fase 1, paso 1 (esqueleto Python, D49); paso 2 bloqueado (storage S3); D50 y D51. Antes: Fase 0.5 y D43–D48 (D47 grano de `fx_rate`; D48 demanda con parque RUNT, marca/modelo sintético).

Este archivo se actualiza al final de cada sesión y funciona como punto de partida para una conversación nueva.

## 1. Fase actual

**Fase actual: Fase 1 — primera ingesta real: EN CURSO (paso 1 cerrado, D49; paso 2 bloqueado).**

Fase 0.5 — investigación de mercado y validación de fuentes: CERRADA, con brechas documentadas.

Brechas (ver `08_market_research.md`, "No encontrado"):

- Parque por marca a nivel nacional: no encontrado. `u3vn-bdcy` trae clase, servicio, estado, departamento y municipio, pero no `marca`.
- Ensamble de carros (Chevrolet, Renault y otras): sin evidencia con fuente oficial.
- Cifras de ANDI-FENALCO leídas por resumen automático; nadie abrió el PDF original (`08_market_research.md`, método y "No encontrado"). Verificar antes de publicar.

Objetivo de la Fase 1: primera ingesta real (`source -> raw MinIO -> manifest -> parser/normalizer -> tests`).

Paso 1 (esqueleto Python) cerrado (D49): hay `pyproject.toml`, `uv.lock`, paquete `pits` (src layout), CLI `pits` (`--help`, `version`), 7 tests y CI mínimo en `.github/workflows/ci.yml`. Sigue sin haber `docker-compose.yml` (paso 2, bloqueado: ver §5).

## 2. Documentación vigente

| Archivo | Versión/estado |
|---|---|
| `00_review_findings.md` | "Auditoría de consistencia" v1.3 (2026-10-10; R1–R3 resueltos por D47 y D48, R6 por D49, R2 renombrada por D51; la original nunca se versionó) |
| `01_project_brief.md` | v2 (2026-10-03) |
| `02_domain_taxonomy.md` | v11 (2026-10-03) |
| `03_data_model.md` | v6 (2026-10-10); `vehicle_registration_stat` renombrada a `vehicle_fleet_snapshot` (D51) |
| `04_infra.md` | v2 (2026-10-03) |
| `05_decisions_log.md` | v7 (2026-10-10); D1–D51 |
| `06_status.md` | vigente (2026-10-10) |
| `07_lessons_learned.md` | vigente, sin versión (2026-10-10) |
| `08_market_research.md` | fechas de consulta 2026-10-03 (antes `claude_08_market_research.md`) |
| `09_us_market_research.md` | tercera ronda, 2026-10-09 (antes `claude_09_us_market_research.md`) |
| `research/parque_por_marca.md` | investigación 2026-10-10 (D50) |

## 3. Terminado

### Fase 0 (dominio y arquitectura conceptual)

- Visión del proyecto como data platform para un marketplace simulado; alcance de producto separado de UI/pagos.
- Taxonomía de partes y vehículos; confianza de contributor y reputación comercial separadas; identidad unificada `account` + roles.
- Modelo de publicaciones, búsquedas, negociaciones, ofertas, órdenes y reseñas; ERD conceptual.
- Convenciones de procedencia e ingesta; raw como payload inmutable antes de parquet (D29).
- Infraestructura local/producción documentada, con reglas mínimas de backups, secrets, healthchecks y límites.

### Fase 0.5 (investigación de fuentes)

- `08_market_research.md` con fichas de datasets, hipótesis validadas/refutadas y lista de "No encontrado".
- D43 (WA DOL como primera fuente de EE. UU., se agrega después de la de Colombia) y D46 (orden de fuentes de Fase 1).
- `09_us_market_research.md`: comparación EE. UU. vs Colombia.
- Flujo de trabajo con agentes: D44 y D45.

### Orden de fuentes (D46, D43)

1. Fase 1: TRM Superfinanciera `32sa-8pi3`.
2. Fase 1b: parque RUNT `u3vn-bdcy`, snapshot mensual.
3. Después: WA DOL `brw6-jymh` (D43).

Justificación por ruta crítica: RUNT va antes que WA DOL porque es parque (STOCK) de Colombia, el mercado principal, y aplica la regla demanda = parque. WA DOL es FLUJO (transacciones) y de EE. UU.

La TRM tiene relevancia de dominio secundaria: los precios del marketplace se fijan primero en COP (confirmado por Henry). Sirve como referencia de costo de importación (Inferencia, `08_market_research.md`). Se elige primero por ingeniería: ejercita el patrón raw -> manifest -> parser sin el ruido del dominio.

### Fase 1, paso 1: esqueleto Python (D49)

- `pyproject.toml` y `uv.lock`; paquete `pits` (src layout); CLI Typer `pits` con `--help` y `version`.
- 7 tests pytest; `ruff check` y `ruff format` en verde.
- Demostrado: `uv sync --locked`; `uv run pits version` → 0.1.0 (Windows); CI verde en GitHub Actions (`.github/workflows/ci.yml`, `setup-uv` fijado a `@v10.3.0`; PR #5).
- Atiende R6 de `00_review_findings.md`: CI mínimo en Fase 1. El CI completo (`dbt build`) sigue en Fase 5 (D40).

### Resueltos por D47 y D48 (2026-10-10)

- R1 (grano de `fx_rate`): D47, fecha única; el normalizer expande el rango de la TRM a una fila por día.
- R2 (entidad y grano del parque RUNT) y R3 (marcas validadas con flujo): D48, demanda solo con el parque RUNT `u3vn-bdcy` por clase/geografía; marca/modelo sintético, calibrado con investigación pública.
- Pregunta de dominio (¿parque RUNT por clase como único insumo de demanda?): respondida por Henry, ver D48.

### Decisiones D50 y D51 (2026-10-10)

- T1: derecho de petición a MinTransporte por parque por marca — descartado (D50); se trabaja con fuentes públicas y el sintético de D48.
- Investigación de fuentes de parque por marca: `docs/research/parque_por_marca.md`.
- D51: `vehicle_registration_stat` renombrada a `vehicle_fleet_snapshot` (stock, no flujo).

### Flujo de trabajo (D44, D45)

- `/orquestar`: arquitecto -> implementador -> revisor-senior -> documentador.
- Henry aprueba solo el plan y el Pull Request. `main` cambia solo vía PR.
- Las ingestas recurrentes van en Airflow, no en agentes.
- Siguen requiriendo aprobación: decisiones D nuevas, preguntas de dominio, comandos destructivos, comandos al VPS y 3 revisiones fallidas seguidas.

## 4. Preguntas abiertas

Las de `05_decisions_log.md` §F. Ninguna bloquea el primer paso de Fase 1.

1. Unidades finales de `quantity_unit`.
2. Normalización geográfica con código DANE desde el MVP o después. Evidencia nueva (`08_market_research.md`, Obj. 6): DIVIPOLA existe como dataset oficial de DANE (`gdxc-w37w`, 1.122 filas, corte 30-dic-2024), pero `u3vn-bdcy` no trae código DANE, solo nombre de municipio. Inferencia de 08: si se usa DANE, Fase 3 necesita una tabla de equivalencias de nombres (tildes, "BOGOTA" vs "BOGOTÁ, D.C."). La decisión sigue siendo de Henry y se vuelve necesaria al llegar a Fase 1b.
3. Reputación comercial: score único o separado buyer/seller.
4. Historial de precio e inventario: core Fase 3 o extensión SCD2.

## 5. Próximo paso — Fase 1

Ordenado por ruta crítica: cada paso depende del anterior. Consistente con D40 (fases por capacidad demostrada), `04_infra.md` §3, §7, §8, §10 y D5/D44.

### Paso 1 — hecho (D49)

**Paso 1: esqueleto del proyecto Python.** Cerrado; ver §3. `pyproject.toml` con `uv`, paquete, CLI Typer, pytest y ruff. Incluye un workflow mínimo de GitHub Actions que solo corre `ruff check`, `ruff format --check` y `pytest -q`, como habilitador. Esto difiere de `01_project_brief.md` §10, que ubica GitHub Actions en Fase 5: allí la capacidad demostrada es el CI completo (lint, unit tests y `dbt build`), que sigue en Fase 5 (D40). Mover CI mínimo a Fase 1 se formalizó en D49 (atiende R6 de `00_review_findings.md`); el CI completo sigue en Fase 5. Va primero porque sin poder testear y correr código ningún otro paso es verificable. Flujo: `/orquestar`, plan aprobado por Henry, rama propia, PR.

### Primer paso para la próxima sesión

**Spike de storage S3 (SeaweedFS) + fila D52 aprobada por Henry**, antes de retomar el paso 2.

**Paso 2 (Docker Compose local, perfil `core`: storage S3 + Postgres, `04_infra.md` §10.1, límites de memoria D9): BLOQUEADO.** MinIO comunitario ya no se distribuye: repo `minio/minio` archivado (2026-04-25), imágenes `minio/minio` y `minio/mc` en 404 en Docker Hub, CVE altos sin parche libre (p. ej. CVE-2026-41145, GHSA-hv4r-mvr4-25vw). Requiere un spike de SeaweedFS (candidato: `chrislusf/seaweedfs:4.48`) y una fila D de storage (siguiente número libre, D52) aprobada por Henry antes de continuar. `04_infra.md` §8.1 guarda `manifest.json` junto al payload en el storage, así que Postgres no es requisito del manifest.

### Pasos siguientes

3. Extractor SODA de TRM: paginación con `$order`, backoff, token opcional (`X-App-Token`, desde variable de entorno). Escribe el payload original en MinIO con la ruta de `04_infra.md` §8.1: `raw/<source_system>/extraction_date=YYYY-MM-DD/batch_id=<uuid>/payload.*`.
4. Manifest de ingesta (`manifest.json`) con los campos de `03_data_model.md` §3 (`source_system`, `ingestion_batch_id`, `ingested_at`, `raw_object_path`, `record_hash` opcional), ID del dataset fijado y atribución. `source_record_id` no aplica: la TRM no trae ID de registro; la llave natural es `vigenciadesde`.
5. Parser/normalizer: casteo de strings, validación de schema y salida normalizada que expande cada rango (`vigenciadesde`-`vigenciahasta`) a una fila por día calendario (D47, grano `rate_date` de `03_data_model.md` §26), deduplicada por fecha para que reejecutar un batch no cree duplicados lógicos; tests unitarios. Documentar cómo reejecutar un batch.

Después: Fase 1b con RUNT `u3vn-bdcy` (snapshot mensual). El DAG de Airflow (D5, D44) corresponde a Fase 4 (`01_project_brief.md` §10), con perfil `orchestration` (`04_infra.md` §10.1).

### Contrato de la fuente TRM (`08_market_research.md`, Ficha 2)

| Atributo | Valor |
|---|---|
| Dataset | `32sa-8pi3`, Superintendencia Financiera de Colombia |
| Endpoint | `https://www.datos.gov.co/resource/32sa-8pi3.json` |
| Licencia | CC BY-SA 4.0 |
| Frecuencia | Diaria |
| Filas | 8.360 al 2026-10-03, desde 1991-12-02 |
| Columnas | `valor` number; `unidad` text; `vigenciadesde` calendar_date; `vigenciahasta` calendar_date |
| Tipos en el JSON | Todo llega como string; se castea en el parser |
| Llave incremental | `vigenciadesde` |
| Autenticación | Ninguna; token opcional `X-App-Token` |

### Riesgos

- Fines de semana y festivos: una fila cubre varios días (`vigenciadesde` 2026-10-03, `vigenciahasta` 2026-10-05). El normalizer expande el rango a una fila por día (D47); raw y manifest conservan el rango original.
- Hay al menos 9 datasets TRM duplicados con esquemas distintos (`mcec-87by`, `ceyp-9c7c`, `djvb-n8kv`, `dit9-nnvp`, otros). Fijar `32sa-8pi3` y verificar atribución en el manifest.
- Rate limit sin token: número exacto no encontrado en la documentación. Registrar un token y manejar reintentos con backoff.
- Paginar siempre con `$order=vigenciadesde` (o `:id`).
- Tope por petición: 50.000 es el límite documentado para Socrata API 2.0; 08 no verificó qué versión sirve datos.gov.co. Con 8.360 filas cabría en una petición, pero se pagina para demostrar el patrón.

### Entregable de Fase 1 (criterios de salida)

- Llamada reproducible, raw payload preservado, batch ID, schema validado, idempotencia, manejo de errores, tests unitarios y documentación de cómo reejecutar un batch.

## 6. Entrada a Fase 1

Condición de entrada cumplida (D46, `08_market_research.md` Ficha 2). Entregable: ver §5.

## 7. Bloqueos y pendientes

- Bloqueo del paso 2 (Docker Compose local): MinIO comunitario ya no se distribuye; falta spike de SeaweedFS y D52 (ver §5).
- Pendiente (Henry): la auditoría semanal (`.github/workflows/claude-recurrente.yml`, D44) no funciona. El `workflow_dispatch` del PR #6 (run 38072914197, 2026-10-10) pasó checkout, setup-uv y `uv sync --locked --no-install-project`, pero falló en `anthropics/claude-code-action@v1`: "Claude Code is not installed on this repository". Acción (Henry): instalar la GitHub App https://github.com/apps/claude en el repo, confirmar el secret `CLAUDE_CODE_OAUTH_TOKEN` y relanzar con `gh workflow run claude-recurrente.yml`.
- Pendiente (Henry): Docker Desktop instalado (cliente 29.8.2); falta arrancar el motor y verificar `docker version` en una sesión nueva.
- Pendiente (Henry): decidir D52 (storage S3).
- Infraestructura: solo Docker está confirmado por Henry. El estado del VPS (Coolify, Metabase y demás servicios) no está auditado.
- Pendiente: auditar el VPS (re-medir lo registrado en `04_infra.md` §4–§6, medición del 2026-10-03 no re-verificada, ver R9, y cumplir el checklist de §15). Requiere confirmación explícita de Henry antes de ejecutar cualquier comando contra el VPS. No bloquea el desarrollo local de Fase 1; bloquea cualquier despliegue.
- Pendiente de dominio: pregunta abierta 2 (DANE), antes de Fase 1b.
- Hallazgos de severidad alta de `00_review_findings.md` (R1–R3): ninguno vigente; resueltos por D47 y D48 (ver §3).

## 8. Regla para la siguiente conversación

Antes de agregar una herramienta o entidad nueva, responder:

1. ¿Qué problema del negocio o del pipeline resuelve?
2. ¿Qué habilidad de Data Engineering demuestra?
3. ¿Cuál es el grano o contrato de datos?
4. ¿Cómo se prueba?
5. ¿Cómo se recupera/reprocesa si falla?

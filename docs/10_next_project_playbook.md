# 10 — Playbook para el próximo proyecto

Última actualización: 2026-10-13
Base: `main` `23d4b09` (PR #25). Fuentes: `docs/07_lessons_learned.md` (lecciones 1–151), `docs/05_decisions_log.md` (D1–D120), `CLAUDE.md`, `.claude/agents/*.md`, `.claude/commands/orquestar.md`, `.github/workflows/ci.yml`, `docker-compose.yml`, `pyproject.toml`, `tests/test_ci_parity.py` y el historial de merges de Git.

Objetivo: arrancar el próximo proyecto con lo que en este costó días. Es un playbook: reglas y checklists, no una narrativa.

**Convenciones de cita**

- `#n` = lección n de `07_lessons_learned.md`. `Dn` = decisión de `05_decisions_log.md`.
- `[Obs]` = observación del orquestador en el hito Fase 5 (2026-10-13), que no está escrita en otro doc. Se usa tal cual se reportó, sin ampliarla.
- **Inferencia** = generalización propia del playbook, no observada como tal en el proyecto.
- Las rutas de plantilla son de este repo (`C:\dev\pits-app`).

---

## 1. TL;DR — 20 reglas de mayor impacto

Ordenadas por tiempo ahorrado o errores evitados (el orden es **Inferencia**, a partir de qué costó más vueltas).

| # | Regla | Origen |
|---|---|---|
| 1 | **Una sola revisión independiente al final del hito** ([Obs], instrucción de Henry). **Inferencia (propuesta, pendiente de D):** revisión por paso solo en pasos de riesgo alto (seguridad, permisos, migraciones o datos reales que no se regeneran). | [Obs]; pendiente de D (ver §3.1) |
| 2 | **Cada entrega a un agente lleva alcance, archivos permitidos, criterios de aceptación y gates como comandos separados.** Sin eso hay vueltas de revisión. | `orquestar.md` Etapa 2; #89 |
| 3 | **Gates sin pipes:** `ruff check`, `ruff format --check` y `pytest` uno por uno, con su exit code. Nunca `cmd \| tail`: el exit code que se ve es el de `tail`. | [Obs] (pipes/`tail`); #151 (gates mal encadenados con `&&`) |
| 4 | **PR en draft hasta la revisión final; avisar "no mergear aún"; verificar el SHA del head antes del merge.** | #149, #102; [Obs] |
| 5 | **CI desde el día 0, con trigger que corra en ramas de trabajo y PR temprano.** El CI falló en ~5 s por un tag inexistente de `setup-uv` (#55). | #55, #147, #49 |
| 6 | **La paridad entre compose y CI la afirma un test que lee los dos YAML**, incluido que cada marker corra en exactamente un job (A∧B incluido). | #142, #150; D112 |
| 7 | **Inspeccionar el proceso real antes de escribir config:** `docker image inspect`, `<bin> -h`, log de arranque y listeners. La ayuda y la documentación pueden no coincidir con el comportamiento real (#130, #129). | #69, #111, #129, #130, #138, #139 |
| 8 | **Superficie de red mínima desde el inicio:** bind a loopback, puertos solo en `127.0.0.1` del host, inventario de listeners antes y después de cada cambio. | #136, #137, #138; D117, D119 |
| 9 | **Secretos:** `.env` local (nunca leído por agentes) + `configs.content` de compose; en CI, secretos efímeros generados en el job. | #130, #143; D104(a), D114, D118 |
| 10 | **Raw write-once y congelado por batch, con manifest y sha256.** La fuente se sobrescribe; lo que no se congela se pierde. | #23, #24, #63, #119; D29, D61, D62, D65 |
| 11 | **Un rol por proceso con mínimo privilegio, probado contra el sistema real.** El Deny de integridad va en el recurso, no en la identidad. | #105, #128, #129; D79, D86, D104 |
| 12 | **Tests que necesitan un servicio: marker + excluido en `addopts` + `pytest.fail` si falta config** (no `skip`). | #75; D58, D84 |
| 13 | **Corridas en vivo en tandas cortas y en serie**, con resultado guardado por tanda; la RAM del host corta procesos largos. | #116, #127; [Obs] |
| 14 | **Pins reproducibles:** imagen por digest, tag exacto de actions, lock fijado al constraints del framework y auditoría del lock tras cada alta. | #55, #104, #117; D57, D60, D94 |
| 15 | **Probe efímero antes de tocar storage o permisos reales; el criterio de aceptación es un hash**, no que arranque. | #131, #141 |
| 16 | **El CLI es el único que lee entorno, reloj y uuid;** la lógica recibe `Mapping` y fábricas, y se prueba offline. | #82, #85, #90 |
| 17 | **Afirmar el efecto, no el valor:** exit code + mensaje, `xfail(raises=...)`, valor efectivo de un parámetro, ruta de subida. | #70, #107, #109, #145 |
| 18 | **Compuertas de calidad antes de publicar:** tests de negocio en staging; el grafo declara cada fuente que un test valida. | #103, #118; D100 |
| 19 | **Docs: cada cifra y cita se verifica con grep o con el log; `06_status.md` se actualiza en el mismo PR; nada vive solo en el chat.** | #43, #46, #47, #59, #87 |
| 20 | **Preflight de checkout (worktree por hito) y un commit por paso**, para reanudar tras una caída sin rehacer. | #89, #101; D73(c) |

---

## 2. Arranque de proyecto (día 0)

Checklist en orden. Cada ítem dice qué copiar de este repo.

### 2.1 Estructura del repo

- [ ] `CLAUDE.md` con comunicación, stack, reglas numeradas y docs bajo demanda. Plantilla: `CLAUDE.md`.
- [ ] `docs/` numerado: brief, taxonomía, modelo, infra, decisiones, status, lecciones. Plantillas: `docs/05_decisions_log.md` (columnas `# | Estado | Decisión | Por qué | Alternativa descartada`), `docs/07_lessons_learned.md` (formato "problema → principio → acción").
- [ ] `06_status.md` con secciones fijas: fase actual, terminado (demostrado / aprobado / pendiente), preguntas abiertas, siguiente paso y §7 de bloqueos y pendientes (#43, #59, #61).
- [ ] Código en `src/<paquete>/` por capa: `sources`, `ingestion`, `storage`, `normalized`, `warehouse`, `transform`, `cli.py`. Plantilla: `src/pits/`.
- [ ] Tests espejo de las capas, más `tests/contract/` (servicios vivos), `tests/pg/` (Postgres real), `tests/orchestration_it/` y `tests/test_ci_parity.py`. Plantilla: `tests/`.
- [ ] dbt en `transform/` con `profiles.yml` versionado sin secretos (D85). Airflow en `orchestration/` como proyecto uv aparte (D94) y compose aparte (D95).
- [ ] `scripts/` para probes y mediciones reproducibles: `scripts/probe_seaweedfs_isolation.sh`, `scripts/ci_seed_warehouse.py`, `scripts/run_dag_and_wait.sh`, `scripts/measure_storage_memory.sh`.
- [ ] Solo citar archivos versionados (`git ls-files`) (#45).

### 2.2 Python: uv, ruff, pytest

Plantilla: `pyproject.toml`.

- [ ] `uv` con `uv.lock` y `.python-version` versionados (D49). Si cambian pisos de dependencias, `uv lock` en el mismo commit; `uv sync --locked` en CI falla si no (#57).
- [ ] Si el módulo importable no se llama como la distribución: `[tool.uv.build-backend] module-name` (#54).
- [ ] `[tool.uv] exclude-dependencies` para transitivas pesadas que no se usan; medir `.venv` antes y después (#104; D85).
- [ ] ruff: `select = ["E", "F", "I", "UP", "B"]`, `line-ending = "lf"` (Windows + Linux).
- [ ] pytest con:
  - `addopts = "-ra --strict-markers --strict-config -m 'not contract and not pg and not airflow'"`;
  - un marker declarado por dependencia externa (`contract`, `pg`, `airflow`);
  - `xfail_strict = true`.
- [ ] El `-m` de la CLI reemplaza el de `addopts` (verificado, #75): un job corre `-m contract` y recibe todos los `contract`, incluidos los `contract and pg`.
- [ ] Al menos un test antes de activar CI: `pytest` sin tests devuelve rc 5 (#49).
- [ ] CLI con Typer y `@app.callback()` desde el primer comando (#56). Tests de CLI por substring, no por layout (#56).

### 2.3 CI con paridad desde el inicio

Plantillas: `.github/workflows/ci.yml` (jobs `ci`, `orchestration`, `pg`, `contract`) y `tests/test_ci_parity.py`.

- [ ] `permissions: contents: read`; `actions/checkout` con `persist-credentials: false` (#58).
- [ ] `astral-sh/setup-uv` con tag exacto (`@v10.3.0`); verificar que el ref exista (#55).
- [ ] Todo workflow instala sus herramientas: `setup-uv` + `uv sync --locked` + `uv run <tool>` (#58).
- [ ] Trigger: `pull_request` y `push` a main, **más** un mecanismo para iterar en ramas. En este repo se usó un trigger temporal que se retiró en un commit aparte (#147). **Inferencia:** `workflow_dispatch` permanente o abrir el PR en draft desde el primer commit evita el trigger temporal.
- [ ] Postgres del job `pg` con `docker run` (no `services:`), la misma imagen@digest, initdb args y límites que compose (#144; D112).
- [ ] Servicios del job `contract` con `docker compose up -d --wait` del mismo compose (D115) y `docker compose down -v` con `if: always()`.
- [ ] Paso "Free disk space" antes de levantar storage que dimensiona por disco libre (#146; D115).
- [ ] Diagnósticos en `if: failure()` que imprimen solo **nombres** de variables, nunca valores.
- [ ] `tests/test_ci_parity.py` desde el primer job con servicios: imagen y args iguales en los dos YAML, credenciales enmascaradas, secretos vaciados en el upload, `addopts` y markers exactos (#142, #150).
- [ ] **Inferencia (extiende #150):** generar la partición desde una tabla `marker → job` y probar que cada combinación de markers usada en `tests/` cae en exactamente un job.

### 2.4 Compose con pins por digest

Plantilla: `docker-compose.yml` (core) + `docker-compose.orchestration.yml`.

- [ ] Toda imagen como `tag@sha256:<digest>`, el digest del índice multi-arch (D57, D60).
- [ ] `mem_limit` = `memswap_limit` por servicio (D9, #14); para servicios Go, ajustar `GOMEMLIMIT` antes de subir el techo (#77; D63).
- [ ] Puertos solo en `127.0.0.1:` del host y con variable para el puerto (`${POSTGRES_HOST_PORT:-5433}`), porque el estándar puede estar ocupado (#78; D60).
- [ ] Healthcheck de Postgres por TCP: `pg_isready -h 127.0.0.1` (#79).
- [ ] `POSTGRES_INITDB_ARGS` con locale explícito (`C.UTF-8`, provider builtin) y un test que lo compruebe en la base real (#142).
- [ ] Componentes opcionales en otro archivo, no en perfiles: compose interpola `${VAR:?}` de todos los servicios aunque el perfil esté inactivo (#110; D95).
- [ ] `docker image inspect` + `<bin> <modo> -h` antes de escribir `command:` (#69).

### 2.5 Secretos

- [ ] `.env` local (git-ignored) y `.env.example` versionado; los agentes leen solo `.env.example` (CLAUDE.md regla 9).
- [ ] Archivos de config con secretos generados por compose con `configs.content` desde `.env`; nada en el host ni en git (Compose ≥ 2.23.1; D104(a), D118).
- [ ] Un solo mecanismo de identidades por servicio: en SeaweedFS 4.48, `AWS_*` y `-s3.config` se **suman** (#130).
- [ ] CI: secretos generados en el job (`secrets.token_urlsafe`), `::add-mask::`, `$GITHUB_ENV`, `test ! -e .env`, y vaciarlos en el step de upload (#143; D114).
- [ ] Excepciones tipadas lanzadas fuera del `except`; imprimir solo `str(exc)`; test con centinela de contraseña (#97).
- [ ] Credenciales de APIs públicas como secreto de entorno, aunque sean gratis (#38). Token por https solamente (D108).

### 2.6 Storage write-once

- [ ] Toda escritura a raw con `IfNoneMatch="*"`; un 412 se reconcilia por contenido (sha256 + longitud), no por ETag (#80, #83, #94; D62, D75).
- [ ] Key determinista con `batch_id`; si la fecha entra en la key, los tests de conflicto fijan el día (#90; D61).
- [ ] Sin permiso de borrado para ingesta; en SeaweedFS `Write` incluye delete, así que el Deny va en la bucket policy (#80, #128; D67, D104(c)).
- [ ] Verificar la policy releída comparando **todas** las claves de cada statement (#134).
- [ ] Probar el contrato con el cliente real y control positivo: el admin de SeaweedFS 4.48 borra con `DeleteObjects` pese al Deny (#73, #129).
- [ ] Objetos grandes: partir en partes ordenadas con hash por parte; no comprimir si el hash es identidad (#120; D98).
- [ ] Registrar el crecimiento: storage inmutable sin lifecycle crece con cada `--force` (#121).

### 2.7 Roles de mínimo privilegio

- [ ] Un rol LOGIN por proceso: owner, loader, reader, transformer, metadata del orquestador (D79, D86, D93).
- [ ] El owner crea los schemas para que el transformer no pueda borrarlos (#105).
- [ ] Matriz de privilegios probada en Postgres real (`tests/pg/test_schema_privileges_pg.py`, `tests/pg/test_transformer_pg.py`).
- [ ] Roles de prueba con sufijo `<uuid8>` por test: los roles son globales del cluster (#99; D84).
- [ ] Identidades S3 separadas (admin / writer / reader) con acciones por bucket (D104). Ver `configs.seaweedfs_s3` en `docker-compose.yml`.
- [ ] El orquestador no recibe credenciales admin (D104(d)).

### 2.8 Inventario de listeners

- [ ] Tras el primer `up`, listar lo que escucha cada contenedor: `/proc/net/tcp` (estado `0A` = LISTEN), no el plan (#138).
- [ ] Apagar lo no usado: en `weed server` 4.48, Iceberg (8181) y Lance (9101) venían abiertos; flags `-s3.port.iceberg=0 -s3.port.lance=0` (#138; D117).
- [ ] Separar `-ip` (dirección para hablar con otros componentes) de `-ip.bind` (socket) (#139).
- [ ] Contrato de red desde **otro contenedor de la misma red**, no desde el host, con control positivo previo (#140; D119). Plantilla: `tests/contract/test_seaweedfs_network_contract.py`.
- [ ] Cada credencial protege solo los caminos que la verifican: probar cada puerto (#137).

---

## 3. Proceso con agentes, versión rápida

Base: `.claude/commands/orquestar.md` y `.claude/agents/{arquitecto,implementador,revisor-senior,documentador}.md`. Henry aprueba solo el plan y el PR (D45, D73(a)).

### 3.1 Cuándo revisar

La regla general es [Obs]; las excepciones por paso son **Inferencia** (propuesta) y deben entrar en la misma D pendiente.

| Tipo de paso | Revisión | Motivo |
|---|---|---|
| Código de capa conocida, docs, tests offline | Solo la revisión final del hito | [Obs]: la revisión por paso con hasta 3 vueltas atrapó bugs reales pero subió mucho el costo. Henry cambió el proceso a una sola revisión al final. |
| Seguridad: secretos, permisos, red, policies | Por paso | Bugs reales atrapados [Obs]: credenciales admin de S3 expuestas en la red, puertos de Iceberg y Lance abiertos, comentario de seguridad engañoso. Ver #136–#138. |
| Migración o cambio sobre datos que no se regeneran | Por paso, con probe previo | **Inferencia:** #131, #141 |
| Cambios de CI (partición de jobs, triggers) | Por paso o con test de paridad | **Inferencia:** [Obs]: 2 tests e2e sin job (#150). |

Pendiente: `orquestar.md` y `revisor-senior.md` siguen diciendo "máximo tres vueltas por paso"; el cambio a revisión final es una instrucción de Henry al orquestador [Obs]. Por la regla 4 de `CLAUDE.md`, formalizarlo con una D nueva (**Inferencia** sobre el procedimiento).

### 3.2 Qué lleva cada entrega

Plantilla de handoff orquestador → implementador (`orquestar.md` Etapa 2.3.a, `implementador.md`):

```text
Paso: S<n> — <objetivo en una línea>
Checkout: <worktree>  Rama: <rama>  Base: <sha>
Decisiones aprobadas: D<n>, D<m> (literal de Henry)
Archivos permitidos: <lista exacta, existentes y nuevos>
Fuera de alcance: <lista>
Criterios de aceptación: <verificables: comando + resultado esperado>
Gates (uno por línea, sin pipes, reportar exit code de cada uno):
  uv run ruff check .
  uv run ruff format --check .
  uv run pytest -q
  <gates del hito: uv run pytest -m pg -q, etc.>
Prohibido: docker compose up/down, VPS, git add ., stash/reset/clean, push a main
Handoff esperado: archivos tocados, git diff --stat, exit codes, pendientes
```

- Gates sin pipes ([Obs]; ver también #151). Si hace falta recortar salida, redirigir a archivo y leerlo después; **Inferencia:** `set -o pipefail` si no hay alternativa.
- Commits con rutas explícitas, nunca `git add .` (`orquestar.md` 2.3.d).
- Handoff con evidencia ejecutada frente a histórica, con fuente y fecha (`implementador.md`, `revisor-senior.md`).

### 3.3 Evitar el merge prematuro

- PR en **draft** desde el primer push; pasar a ready solo después de la revisión final y los gates ([Obs]; #55 recomienda abrir el PR temprano para ver el CI).
- Avisar explícitamente a Henry: "no mergear aún" mientras haya commits pendientes [Obs].
- Antes del merge, comparar el SHA del head del PR con los commits del hito (#149). El PR #22 se mergeó sin el paso S3; hubo que abrir otro PR [Obs]; #149.
- PR apilados: mergear de abajo hacia arriba y retargetear a `main` (#102). Verificar con `gh pr view` que el commit está en `main`.

### 3.4 Paralelismo frente a RAM

- Paralelizar solo lecturas o escrituras disjuntas, con entorno coordinado (`orquestar.md`; `uv sync` y pytest comparten `.venv`).
- En Windows con Docker/WSL2, no correr en paralelo suites con servicios: los procesos largos en segundo plano se cortaron por RAM (#116, #127; [Obs]: "hubo que ir en serie").
- Medir el margen del host antes de una corrida larga (#13, #127).
- Suites largas en partes repetibles (#127: rápidos, `test_runt_*` por separado, lock y SeaweedFS caído).

### 3.5 Pasos en vivo: los hace el orquestador

- Los subagentes no tienen permiso para `docker compose up` [Obs]; `implementador.md` lo prohíbe sin autorización y `orquestar.md` lo lista como motivo para interrumpir a Henry.
- Por tanto, el plan debe separar los pasos offline (implementador) de los pasos en vivo (orquestador): levantar servicios, `pits storage init`, corridas reales, `-m contract`, `-m pg`, `-m airflow`, mediciones.
- **Inferencia:** agrupar todos los pasos en vivo al final del hito, en una sola sesión con el stack arriba, ahorra levantar y bajar el stack varias veces.
- Desde Git Bash: `MSYS_NO_PATHCONV=1` en comandos de Docker (#114); JSON en `bash -c` con comillas simples (#125).

### 3.6 Reanudar tras una caída

- `git status` y `git diff` antes de continuar; comprobar qué efectos ya ocurrieron (contenedores reiniciados, objetos escritos) (#101).
- Un commit por paso; cada paso idempotente (#101, #37).
- Trabajo largo de investigación: un archivo por ítem + `progress.json` (#37).

### 3.7 Docs y decisiones

- Toda decisión nueva = fila D aprobada antes de implementar; en filas viejas solo cambia la celda Estado (CLAUDE.md regla 4; D73(b)).
- Al cambiar alcance, listar qué D previas toca y registrar sucesoras (#88).
- Citar la aprobación literal de Henry en la fila D (#50).
- Verificar cada cita con grep y cada cifra contra el log (#47, #39, #87). Hubo correcciones repetidas por cifras y commits mal atribuidos [Obs].
- Citar `06` por sección, docs estables por línea (#46).
- Un hallazgo de auditoría se re-contrasta con la fuente primaria antes de aplicarlo (#62, #44).
- Comparar contra la versión anterior antes de aceptar una reescritura; contar filas no basta (#35; `documentador.md`).
- El documentador no tiene Bash: la comparación contra `base_commit` la hace el revisor (`documentador.md`).

---

## 4. Patrones técnicos que funcionaron

Cadena: **fuente → raw (batch + manifest) → normalize → loader → dbt → Airflow**.

### 4.1 Fuente y extracción

- Cliente HTTP con timeouts explícitos (D64).
- Antes de paginar, `count(*)` con el mismo filtro; si no cuadra, exit 3 "Truncated extraction" y sin manifest (#135; D105).
- Llave incremental = llave de negocio estable, no `:id` ni `:updated_at` si la fuente se reemplaza completa (#86).
- Watermark = high-water mark arrastrado: un batch vacío conserva el previo (#84; D66).
- Frescura real con `rowsUpdatedAt`, no `viewLastModified` (#65).
- Validar en origen lo que la tabla rechazaría (caracteres Cc, fechas < 1900) con exit 1 (#123; D103); medir la forma de la regla con datos reales (regex 4,5× más rápida, #124).
- Inspeccionar tipos reales con `curl` a la API (en SODA todo llega como string, #62).
- Revisar términos y `robots.txt` por fuente (#16).

**Gotchas**

- Un umbral fijado con una sola muestra es hipótesis: aviso, no límite duro (#95; D76(f)).
- Series oficiales con huecos documentados: los tests de completitud los permiten (#40).

### 4.2 Raw y manifest

- Payload original primero, en su formato; parquet o CSV después (#23; D29).
- Metadata mínima: `batch_id`, `source_id`, timestamp, raw path (#24; D36, D65).
- Snapshot por publicación, porque la fuente solo expone el corte vigente (#63, #119; D96).
- `put_once` con reconciliación por contenido (`already_identical`) (#94; D75).

**Gotchas**

- Reintento + write-once = 412 sobre tu propia escritura (#83).
- Probar el multipart afirmando el sufijo `-N` del ETag, no solo el contenido (#70).
- El presupuesto de memoria de subida lo fijan chunks × parte, no el tamaño del objeto (#71).

### 4.3 Normalize

- Replay = baseline (último full) + aplicación ordenada de posteriores; nunca "unir todos los batches" (#91; D76).
- `since` como snapshot de cola, para que un borrado de cola falle por cobertura (#93; D76(c)).
- Artefacto determinista con `content_sha256` y partes de 20.000 filas (#120; D98).
- Orden por PK en puntos de código, emparejado con `COLLATE "C"` en Postgres (#122).
- Rangos de vigencia expandidos a una fila por día (date spine), conservando el raw (#52; D47).
- El normalizer no lee el reloj (#90).

**Gotchas**

- Identidad del artefacto por batch: `--force` crea otro artefacto aunque la fuente no cambie (#121).
- Tests de orden con al menos dos elementos desordenados (#92).

### 4.4 Loader a Postgres

- Migraciones en dos capas: bootstrap Python idempotente + SQL numerado en `ops.schema_migrations` (D80).
- `ops.load_run` append-only (D81).
- Verificación end-to-end en la misma transacción: reconstruir el CSV desde la base y comparar sha256 antes del COMMIT (#100; D82).
- CHECK de rango que excluye `NaN` e `Infinity` (#98).
- Advisory lock con una clave única por recurso y prueba de exclusión de todas las parejas (#106; D90).
- Clasificación de errores del driver por evidencia del handshake si falta SQLSTATE (#96; D83).

**Gotchas**

- En tablas acumulativas, la aserción se acota a la partición cargada (#126; D99).
- El conteo de filas no prueba contenido (#11, #100).

### 4.5 dbt

- Rol transformer propio: lee `landing`, escribe solo sus schemas (#105; D86).
- Tests de negocio sobre `ref('stg_...')`, para que fallen antes de materializar el mart (#103).
- `-- depends_on: source(...)` cuando un test tiene dos padres (#118; D100).
- Normalización de categorías con seed versionado + `accepted_values` (#64, #66).
- Freshness con warn y error (D85–D88).
- `--select` con allow-list `^tag:[a-z_]+$` (D101).

**Gotchas**

- Auditar el lock al añadir dbt (`dbt-core-experimental-parser`, #104).
- Con alta varianza, 3 corridas no bastan; la regla de aceptación se fija antes de medir (#132; D110).

### 4.6 Airflow

- Proyecto uv aparte con `constraint-dependencies` del framework: 0 diferencias con la imagen (#117; D94).
- Imagen slim: declarar `psycopg2-binary` y `asyncpg` con `--require-hashes` (#112; D89).
- uv solo en build (`RUN --mount`) e invocado por ruta absoluta (#111; D89).
- `UV_COMPILE_BYTECODE=1`: arranque −47 % (#133; D111).
- Operador que lanza el subproceso en su propio grupo y lo mata ante timeout (#113; D92).
- Ventana de datos por parámetro, no por `logical_date` (#115; D92).
- Retención de logs como DAG propio (D109).

**Gotchas**

- `_CMD` no recorta el salto de línea: `sys.stdout.write` sin `\n` (#108; D93).
- `retry_exponential_backoff=True` = 1.0 en 3.3.2; usar `2.0` y probar el valor efectivo (#109; D92).
- `airflow tasks clear` siempre con `-s` y `-e` (#115).
- ESRCH de procfs = proceso muerto (#148).
- La integración `-m airflow` tarda unos 23 min la suite completa (`06_status.md` §7) y unos 10 min por test [Obs].

---

## 5. Errores que no repetir

### 5.1 CI

| Síntoma | Causa | Regla preventiva | Origen |
|---|---|---|---|
| Dos e2e existen pero ningún job los corre | Partición `A and not B` / `B and not A` deja fuera A∧B | Test de paridad que exige que cada test marcado corra en exactamente un job | #150 |
| Commit roto subido (#151) | Gates mal encadenados con `&&` (#151); con pipes o `tail` el exit visible es el de `tail` ([Obs]) | Un comando por gate, exit code de cada uno | #151; [Obs] |
| Push de rama no dispara CI | Trigger solo `pull_request`/`push` a main | Trigger temporal retirado en commit aparte, o PR draft temprano | #147 |
| `setup-uv@v10` falla | No hay tag flotante de major | Tag exacto y verificar el ref | #55 |
| Workflow semanal falla por `ruff` no instalado | El workflow no instala sus herramientas | `setup-uv` + `uv sync --locked` en cada workflow; probar con `workflow_dispatch` | #58 |
| CI falla con `uv sync --locked` | Pisos cambiados sin `uv lock` | Regenerar lock en el mismo commit | #57 |
| `pytest` rc 5 | Sin tests | Al menos un test antes del CI | #49 |
| `services:` no reproduce el Postgres real | No admite initdb args ni límites; arranca antes de crear credenciales | `docker run` en un step | #144; D112 |
| 15 "failed to find writable volume" | `-volume.max=0` dimensiona por disco libre del runner | Liberar disco + diagnósticos `/dir/status` en fallo | #146; D115 |
| Un `xfail` pasa por cualquier error | `xfail` sin `raises=` | `xfail(strict=True, raises=...)` | #145 |
| `workflow_dispatch` falla por causa externa y se mergea igual | Sin registro | Anotar en `06` §7 con run ID, o no mergear | #61 |

### 5.2 Docker y SeaweedFS

| Síntoma | Causa | Regla preventiva | Origen |
|---|---|---|---|
| Config no aplica como se planeó | `Cmd` y entrypoint de la imagen anteponen flags | `docker image inspect` + `-h` del modo antes del compose | #69 |
| Aislamiento de identidades anulado | `AWS_*` y `s3.json` se suman | Un solo mecanismo; verificar con key falsa | #130 |
| Puertos 8181 y 9101 abiertos sin saberlo | `weed server` abre servicios no documentados | Inventario de listeners antes y después | #138; [Obs] |
| Filer y master sin auth en la red Docker | Bind en todas las interfaces | `-ip.bind=127.0.0.1` y solo los puertos necesarios en la red | #136; D117 |
| S3 no llega al filer tras restringir | `-ip` ≠ `-ip.bind` | Fijar ambos y probar con el contrato | #139 |
| Prueba de aislamiento da "cerrado" falso | Se probó desde el host | Probar desde otro contenedor de la red | #140 |
| Core roto sin variables de Airflow | Compose interpola todos los servicios | Archivo compose aparte | #110 |
| Puerto 5432 ocupado | Postgres nativo de Windows | Puerto por variable | #78 |
| Contenedor healthy antes de aceptar TCP | `pg_isready` por socket durante initdb | `pg_isready -h 127.0.0.1` | #79 |
| Pico de memoria subestimado | `docker stats` muestrea cada ~3 s | `memory.peak` del cgroup tras restart | #72 |
| Rutas de Windows dentro del contenedor | Git Bash convierte rutas | `MSYS_NO_PATHCONV=1` | #114 |
| Versión fijada de una herramienta no es la que corre | La imagen base trae otra antes en el PATH | Ruta absoluta y verificar en el contenedor | #111 |

### 5.3 Postgres y dbt

| Síntoma | Causa | Regla preventiva | Origen |
|---|---|---|---|
| `rate > 0` acepta NaN | En `numeric`, NaN es mayor que todo | CHECK que excluye `NaN` e `Infinity` | #98 |
| Hash del CSV reconstruido no cuadra | Colación de la base ≠ orden de Python | `COLLATE "C"` | #122 |
| Tests pg se pisan / roles huérfanos | Roles globales del cluster | Roles con sufijo `<uuid8>` por test | #99 |
| Mart malo reemplaza al bueno | Test singular sobre el mart corre después de materializar | Tests de negocio en staging | #103 |
| Test fallido no bloquea el mart | dbt solo salta descendientes de todos los padres | `depends_on` explícito | #118 |
| Locks no excluyen procesos | Claves coincidentes por accidente | Clave única y prueba por parejas | #106 |
| Test acepta un exit 3 por otra causa | Solo se afirma el código | Afirmar código y mensaje | #107 |
| Error de conexión sin SQLSTATE | psycopg 3.3 no lo entrega | Clasificar por `pgconn.used_password` | #96 |
| `.venv` inflado | Transitiva con binario de 261 MB | Auditar lock, `exclude-dependencies` | #104 |

### 5.4 Airflow

| Síntoma | Causa | Regla preventiva | Origen |
|---|---|---|---|
| `database "airflow_meta\n" does not exist` | `_CMD` no recorta `\n` | `sys.stdout.write` sin salto; test byte a byte | #108 |
| Sin backoff real | `True` = multiplicador 1.0 | Valor numérico y test del efecto | #109 |
| Subprocesos huérfanos tras timeout | SIGALRM no mata hijos | Grupo propio + SIGTERM/SIGKILL | #113 |
| `tasks clear` afecta todas las corridas | Sin `-s`/`-e` | Siempre con ventana | #115 |
| Test flaky en `orchestration` | ESRCH de procfs tratado como error | ESRCH = proceso muerto | #148; [Obs] |
| Tests prueban otro Airflow | Lock aparte con 52 diferencias | `constraint-dependencies` del framework | #117 |
| Metadata DB sin driver | Imagen slim | Declarar drivers con hashes | #112 |

### 5.5 Python y tests

| Síntoma | Causa | Regla preventiva | Origen |
|---|---|---|---|
| Tests frágiles por reloj/uuid | Parches globales | Fábricas inyectadas | #85 |
| Test de conflicto no prueba nada | La fecha forma parte de la key | Fijar el día, variar la hora | #90 |
| Test de orden vacuo | Un solo elemento | Dos elementos desordenados | #92 |
| Test de servicio pasa en verde sin servicio | `skip` por config faltante | `pytest.fail` | #75 |
| Medición con falso verde | `RUNS=0` | Validar parámetros al inicio | #81 |
| Secreto en traceback | `__context__` arrastra el `pgconn` | Lanzar fuera del `except` | #97 |
| Subcomando desaparece | Typer colapsa una app de un comando | `@app.callback()` | #56 |
| "Expected a Python module" | Módulo ≠ distribución | `module-name` | #54 |
| Umbral de memoria falla sin bug | Atado al tamaño del dato | Atarlo a la config | #71 |

### 5.6 Docs y proceso

| Síntoma | Causa | Regla preventiva | Origen |
|---|---|---|---|
| Cita inventada o fase equivocada en docs | No se verificó con grep | Revisor que verifica citas | #47 |
| Cifras y commits mal atribuidos | Resumen sin contrastar con el log | Cada cifra con unidad, contrastada con el log | #87, #39; [Obs] |
| `06` desactualizado una semana | Status "cuando haya tiempo" | Actualizar en el PR que cierra el paso | #43 |
| Pendientes perdidos | Vivían solo en el chat | Todo pendiente en `06` o en una D | #59 |
| Evidencia borrada en una revisión | Reescritura aceptada sin comparar | Comparar contra la versión anterior | #35 |
| Cambio de PR apilado no llega a main | Merge contra la rama base | Retarget a main | #102 |
| Paso fuera del merge | Commits empujados durante el merge | PR draft + SHA del head | #149; [Obs] |
| Trabajo a medio editar tras límite de API | Caída a mitad de paso | `git status`/`git diff` antes de reanudar | #101 |
| Checkout ajeno en riesgo | `git switch main && git pull` sin preflight | Preflight D73(c), worktree por hito | #89 |
| Premisa falsa en la tarea | No se leyó la fuente | Leer la fuente antes de actuar | #44, #50 |
| Contradicciones entre docs | Corrección silenciosa | D nueva | #48 |
| Mediciones largas sin evidencia | RAM del host corta el proceso | Tandas cortas, en serie | #116, #127 |
| Tendencia con corridas no comparables | Cargas distintas | Fijar carga; reportar rango | #74 |
| Unidades mezcladas | MiB vs MB | MiB para memoria; bytes literales del log | #87, #76 |

### 5.7 Seguridad

| Síntoma | Causa | Regla preventiva | Origen |
|---|---|---|---|
| Credenciales admin de S3 alcanzables en la red | Scheduler con admin; filer sin auth | Identidades por proceso, bind a loopback | D104(d), D117; [Obs] |
| Comentario de seguridad engañoso | Afirmación no probada | Cada afirmación de seguridad con test o probe | [Obs]; #129 (**Inferencia** de la regla) |
| La policy no bloquea al admin | `DeleteObjects` lo salta | Probar con el cliente real; `xfail(strict)` + limitación | #129 |
| 403 tomado como inmutabilidad | Sin control negativo | Control positivo con la misma identidad | #73 |
| Write-once burlado | delete + put | Quitar delete; Deny en el recurso | #80, #128 |
| JWT no cubre el gRPC | La credencial solo protege su camino | Probar cada puerto | #137 |
| Secreto persistente en GitHub | Secrets de repo | Efímeros por job | #143 |
| Sdist que ejecuta código al instalar | Transitiva no revisada | Auditar lock | #104 |
| Token por http | Base no https | Rechazar con exit 1 | D108 |

---

## 6. Estimaciones reales

Solo datos que están en Git o en los docs. **Lapso** = del primer commit de la rama al merge (`git log` de cada merge). No incluye el tiempo de plan y aprobación anterior al primer commit, ni las pausas nocturnas: no mide esfuerzo.

| Hito (rama) | Commits | Lapso | Qué lo alargó (según docs) |
|---|---|---|---|
| Esqueleto Python (`chore/fase1-paso1-skeleton`) | 7 | 11 min (10-10) | #54, #55, #56 |
| Spike SeaweedFS (`spike/seaweedfs`) | 8 | 62 min (10-10) | Mediciones de memoria y multipart (#70–#77) |
| Storage y Postgres local (`feat/phase1-step2-storage`) | 8 | ~2 h (10-10) | #78, #79 |
| Extractor TRM (`feat/phase1-step3-trm-extractor`) | 8 | 55 min (10-10) | #83–#86 |
| TRM normalize (`feat/trm-normalize`) | 7 | ~5,5 h (10-11) | Revisión del plan: #91–#93 |
| Loader fx_rate (`feat/fx-rate-loader`, apilado) | 9 | ~4 h (10-11) | #96–#100; PR apilado #102. El corte por límite de API de #101 está entre lecciones del loader (**Inferencia**: ocurrió en este hito) |
| dbt fx_rate (`feat/dbt-fx-rate`) | 6 | 17:55 → 09:35 del día siguiente | #103–#107; S1, S3 y S4 en vuelta 2 de revisión (`06` §3) |
| Airflow TRM (`feat/airflow-trm`) | 7 | ~5 h (10-12) | #108–#117; RAM (#116) |
| RUNT parque (`feat/runt-fleet-snapshot`) | 8 | 16:55 → 07:41 del día siguiente | #118–#127; RAM (#127) |
| Endurecimiento (`feat/hardening-optimization`) | 8 | 23:39 → 08:03 | #128–#135; probes (#131) |
| CI completo (`feat/ci-full`) | 4 | 27 min (10-13) | Mergeado sin el paso S3 (#149) |
| Aislamiento de listeners (`feat/seaweedfs-listener-isolation`) | 5 | 40 min (10-13) | #136–#141 |
| Fix ESRCH (`fix/operator-test-esrch`) | 1 | 11 min | #148 |
| CI contract (`feat/ci-contract`) | 10 | 48 min (10-13) | #146, #147, #150, #151 |
| PR de docs y decisiones (`docs/*`) | 1–14 | 2–56 min | Correcciones de citas (#45–#48) |

Tiempos de ejecución registrados:

- `pytest -m pg`: 120 passed en unos 2 minutos (`06_status.md` §3, hito dbt).
- Suite `-m airflow`: ~23 min (`06_status.md` §7); unos 10 min por test de integración [Obs].
- Iteración de CI: unos 5 min por vuelta [Obs]. Fallo por tag inexistente de `setup-uv`: ~5 s (#55).
- dbt build: 7,7 / 9,5 / 18,1 s (#132; D110).
- Arranque `pits version`: 1,391 → 0,714 s con bytecode precompilado (#133; D111).

Calendario: 24 PR mergeados entre el 2026-10-10 11:39 y el 2026-10-13 10:33 (`git log --merges`). Las decisiones D44–D120 están fechadas entre el 2026-10-10 y el 2026-10-13; D43, el 2026-10-09.

Patrones (**Inferencia** a partir de la tabla):

- Los hitos con servicios vivos (Airflow, RUNT, endurecimiento, loader) son los de lapso de horas; los offline o de docs, de minutos.
- Lo que más alargó fue lo que corre en vivo y la RAM (#116, #127), más las vueltas de revisión por paso [Obs].
- Los PR cortos al final (CI, listeners, fix) se beneficiaron de las plantillas ya existentes.

Sin datos: duración del plan y de la aprobación de cada hito, tiempo de cada vuelta de revisión y número total de vueltas por hito. No se estiman.

---

## 7. Contraste DA → DE

Solo donde cambia la forma de trabajar.

| Tema | En DA/DS | En DE | Origen |
|---|---|---|---|
| Código | Notebook con estado oculto | Módulos, CLI y tests | #7; CLAUDE.md regla 1 |
| Datos de la fuente | Consultar la tabla viva | Congelar cada versión en raw con batch | #63, #119 |
| Grano | Agregar sin revisarlo | El grano es el contrato | #4, #22, #51 |
| Calidad | Revisar el dashboard después | Compuerta que bloquea antes de publicar | #103 |
| Integridad | Contar filas | Comparar sha256 | #11, #100 |
| Configuración | `os.environ` en cualquier función | El CLI lee el entorno; la lógica recibe un `Mapping` | #82 |
| Credenciales | Usuario admin de dbt; credencial de prueba en el repo | Rol por proceso; secretos efímeros | #105, #143 |
| Herramientas | Caja negra | Contrato inspeccionado (imagen, puertos, flags) | #69, #138 |
| Pruebas | Comprobar que corre | Afirmar el efecto y la causa | #107, #109 |
| Entornos | "Funciona en mi máquina" | Paridad afirmada por test | #117, #142 |
| Alcance y decisiones | Se edita en el lugar | Contrato versionado con sucesoras | #88 |
| Reintentos | Repetir hasta que pase | Idempotencia demostrable por contenido | #94 |

---

## 8. Dominio y método de análisis (para reutilizar en proyectos de datos)

No son de infraestructura, pero evitan rehacer modelos.

- Nombrar la semántica antes que la fuente: stock vs flujo (#60; CLAUDE.md regla 5), reputaciones distintas (#20, #31).
- El grano incluye todas las dimensiones que distinguen una fila y los participantes de la transacción (#22, #31; D32, D41).
- Clasificaciones en la entidad obligatoria, no en una tabla opcional (#36; D42).
- Una identidad, varios roles (#27; D30).
- Si el producto promete una interacción, el modelo tiene su evento (#21; D33).
- Snapshots de condiciones cambiantes al momento del evento (#19; D14).
- Audit log con payload completo (#28; D37).
- Hechos primero, scores después; probar topes, transiciones y bordes de cada fórmula (#18, #29, #32, #33, #34).
- Categorías oficiales: contar antes de nombrar, decir sobre qué grano se cuenta y mapear distribuidores a marcas antes de calcular proporciones (#64, #66, #67, #68).
- Reclasificaciones de códigos y unidades homónimas: dimensión de equivalencias con vigencia (#41, #42).
- Real y sintético nunca en la misma métrica (#53).
- Evidencia de mercado: fuente verificable, totales recalculados de forma independiente (#15, #17, #39; CLAUDE.md regla 6).
- Lecciones del proyecto anterior que siguen vigentes: #1–#12 (columnas, tipos, granularidad, `LIMIT` antes de filtrar, materialidad, correlación).

---

## 9. Primer día del próximo proyecto, en orden

1. Copiar `CLAUDE.md`, `.claude/agents/`, `.claude/commands/orquestar.md` y el esqueleto de `docs/`; ajustar el dominio.
2. Registrar en D1–Dn el stack, el proceso de revisión (final del hito; las excepciones de §3.1 solo si se aprueban en esa D) y la política de secretos.
3. Python: §2.2.
4. CI con paridad: §2.3 (job `ci` primero, PR en draft para verlo correr).
5. Compose y secretos: §2.4 y §2.5.
6. Storage write-once: §2.6.
7. Roles de mínimo privilegio: §2.7.
8. Inventario de listeners: §2.8; después los jobs `pg` y `contract` con `tests/test_ci_parity.py`.
9. Recién entonces la primera fuente: extractor → raw → normalize → loader → dbt → orquestador.

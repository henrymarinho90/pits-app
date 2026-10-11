# 06 — Estado del proyecto

Última actualización: 2026-10-10
Estado: paso 3 de Fase 1 (extractor TRM) implementado en PR, con evidencia de corrida real; D64–D67 aprobadas por Henry el 2026-10-10 y registradas en `05` (v11). Siguiente paso: normalización TRM (D47) y replay desde raw (sin implementar). Antes: paso 2 de Fase 1 (storage y Postgres locales, perfil `core`) CERRADO en PR; D60–D63 aprobadas por Henry el 2026-10-10 y registradas en `05` (v10). Antes: D57 (storage SeaweedFS, memoria M1 768m, inmutabilidad opción A), D58 (marker `contract`) y D59 (demanda solo `ACTIVO`) aprobadas por Henry el 2026-10-10 y registradas en `05` (v9). Antes: spike de storage SeaweedFS 4.48 completado en la rama `spike/seaweedfs` (`docs/spikes/seaweedfs.md`; 14/14 tests de contrato y 30 offline); Fase 1 paso 1 cerrado (D49). Antes: spike planeado y bloqueo de storage (sin evidencia); segunda ronda regional y D52–D56 (calibración del parque con Boyacá y Risaralda, marca primero, servicio público aparte, alcance de la demanda). Antes: D50 y D51; Fase 0.5 y D43–D48 (D47 grano de `fx_rate`; D48 demanda con parque RUNT, marca/modelo sintético).

Este archivo se actualiza al final de cada sesión y funciona como punto de partida para una conversación nueva.

## 1. Fase actual

**Fase actual: Fase 1 — primera ingesta real: EN CURSO (pasos 1, 2 y 3 implementados: D49, D60–D63 y D64–D67; paso 3 en PR; siguiente: normalización TRM).**

Fase 0.5 — investigación de mercado y validación de fuentes: CERRADA, con brechas documentadas.

Brechas (ver `08_market_research.md`, "No encontrado"):

- Parque por marca a nivel nacional: no encontrado. `u3vn-bdcy` trae clase, servicio, estado, departamento y municipio, pero no `marca`.
- Parque por marca a nivel subnacional: parcial. Boyacá y Risaralda sirven de calibración (D52, D55); el resto tiene datos viejos o sin cobertura (§3, "Investigación regional").
- Ensamble de carros (Chevrolet, Renault y otras): sin evidencia con fuente oficial.
- Cifras de ANDI-FENALCO leídas por resumen automático; nadie abrió el PDF original (`08_market_research.md`, método y "No encontrado"). Verificar antes de publicar.

Objetivo de la Fase 1: primera ingesta real (`source -> raw SeaweedFS (D57) -> manifest -> parser/normalizer -> tests`).

Paso 1 (esqueleto Python) cerrado (D49): hay `pyproject.toml`, `uv.lock`, paquete `pits` (src layout), CLI `pits` (`--help`, `version`), 7 tests y CI mínimo en `.github/workflows/ci.yml`. Paso 2 cerrado (en PR): `docker-compose.yml` (perfil `core`), `pits storage init` y bucket `pits-raw` (ver §3).

## 2. Documentación vigente

| Archivo | Versión/estado |
|---|---|
| `00_review_findings.md` | "Auditoría de consistencia" v1.3 (2026-10-10; R1–R3 resueltos por D47 y D48, R6 por D49, R2 renombrada por D51; la original nunca se versionó) |
| `01_project_brief.md` | v3 (2026-10-10); MinIO reemplazado por SeaweedFS (D57) |
| `02_domain_taxonomy.md` | v12 (2026-10-10); `fleet_operator` (D54) |
| `03_data_model.md` | v9 (2026-10-10); mapeo del manifest en §3 (D65, D66); `vehicle_registration_stat` renombrada a `vehicle_fleet_snapshot` (D51); desglose por servicio y marca primero (D52–D56); filtro `ACTIVO` (D59) |
| `04_infra.md` | v5 (2026-10-10); §8.1 con el contrato del batch raw (D65); perfil `core` (D60–D63); GOMEMLIMIT SeaweedFS 500MiB (D63); bucket `pits-raw` (D61) |
| `05_decisions_log.md` | v11 (2026-10-10); D1–D67 (D60–D63 aprobadas 2026-10-10; D64–D67 aprobadas 2026-10-10) |
| `spikes/seaweedfs.md` | spike SeaweedFS 4.48 (2026-10-10), mergeado en `main` (PR #9); incluye los borradores D57 y D58 (aprobados; ver `05`) |
| `06_status.md` | vigente (2026-10-10) |
| `07_lessons_learned.md` | vigente, sin versión (2026-10-10) |
| `08_market_research.md` | fechas de consulta 2026-10-03 (antes `claude_08_market_research.md`) |
| `09_us_market_research.md` | tercera ronda, 2026-10-09 (antes `claude_09_us_market_research.md`) |
| `research/parque_por_marca.md` | investigación 2026-10-10 (D50); segunda ronda 2026-10-10, sección "Segunda ronda" (base de D52 y D55) |

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

### Fase 1, paso 2: storage y Postgres locales (D57, D60–D63; en PR)

- `docker-compose.yml` (`name: pits`, perfil `core`): SeaweedFS 4.48 (`server -s3`, `127.0.0.1:8333`, `GOMEMLIMIT` 500MiB, `mem_limit` = `memswap_limit` 768m) y Postgres 17.11 Debian con digest fijo (`127.0.0.1:${POSTGRES_HOST_PORT:-5433}`, `mem_limit` = `memswap_limit` 1g, `shm_size` 256m, initdb con `C.UTF-8` builtin). `docker-compose.spike.yml` sin cambios.
- Memoria (D63): 3/3 corridas `-m contract` verdes, sin OOM. Picos `memory.peak` 526,1 / 513,4 / 538,0 MiB frente a un límite de 684510412 B (85 % de 768 MiB). Con GOMEMLIMIT 600MiB la corrida 2 dio 86 % (criterio no cumplido). Postgres: lectura puntual de `memory.current` = 130818048 B (~125 MiB) tras el primer up, 2026-10-10; sin log guardado.
- Bucket `pits-raw` con versioning y sin Object Lock (D61): `pits storage init` dos veces, primero created=true/changed=true y después created=false/changed=false.
- Write-once (D62): `tests/contract/test_conditional_put_contract.py` con `IfNoneMatch="*"`: 2.º put → 412, contenido intacto, 1 versión.
- Tests: offline (`uv run pytest -q`) con `botocore.stub.Stubber` para `load_storage_settings` y `ensure_raw_bucket`, y CLI `pits storage init` con `CliRunner`. Contrato: `uv run --env-file .env pytest -m contract -q`.
- Cierre del plan (paso 7, 2026-10-10): `ruff check` y `ruff format --check` OK, `pytest -q` 90 passed (22 contract deselected); `docker compose down` sin `-v` (volúmenes `pits_postgres_data`, `pits_seaweedfs_data` y `pits_spike_seaweedfs_data` conservados).

### Fase 1, paso 3: extractor TRM (D64–D67; en PR)

- Código: cliente SODA con reintentos y timeouts (`src/pits/sources/soda/`, D64); raw store write-once y manifest v1 (`src/pits/ingestion/`, D65); extractor de la TRM (`src/pits/sources/trm/`, D66); CLI `pits extract trm`. Tests offline con `httpx.MockTransport` y `MemoryRawStore`; contrato contra SeaweedFS (`tests/contract`).
- `CLAUDE.md` (Stack) ya dice SeaweedFS; lo editó Henry y se comitea en este PR.
- Corrida real del 2026-10-11 UTC contra datos.gov.co, con SeaweedFS local:
  - 1.ª corrida (sin batch previo; `incremental` se registra como `mode=full`): 8.365 filas, 9 archivos `payload-*.json`, 1.001.892 bytes (≈ 0,96 MiB), watermark hasta 2026-10-10, 5,5 s.
  - 2.ª corrida (incremental): 0 filas; arrastra el watermark (2026-10-10), 1,7 s.
- Tests: `uv run --env-file .env pytest -m contract` 28 passed; `uv run pytest -q` 296 passed.
- Memoria (criterio D63, `scripts/measure_storage_memory.sh`, `memory.peak` del contenedor SeaweedFS): 3/3 corridas `-m contract` (26 tests; medidas antes de añadir los 2 últimos tests de contrato de TRM) con picos 499,8 / 515,6 / 515,8 MiB (524120064 / 540663808 / 540880896 B), frente a 652,8 MiB (684510412 B = 85 % de 768 MiB). Sin OOM.
- Cómo reejecutar (D66):
  - `uv run --env-file .env pits extract trm`: incremental desde el watermark (`vigenciadesde > watermark`, sin relectura). Sin batch committed, hace backfill completo desde 1991-12-02 y lo registra como `mode=full`; la salida imprime el modo efectivo.
  - `--full`: recarga todo el dataset.
  - `--since YYYY-MM-DD`: recarga desde esa fecha inclusive. Si deja un hueco respecto al watermark (más de un día después), sale con exit 2.
  - Cada corrida crea un batch nuevo (`batch_id` uuid4). Nunca sobrescribe batches previos; un batch sin `manifest.json` es huérfano y se ignora.
  - Las fechas (`extraction_date`, `started_at`, `finished_at`) van en UTC. `extraction_date` es la fecha UTC de `started_at`.
- Exit codes: 0 committed; 1 error permanente o de configuración (esquema cambiado, manifest corrupto, 412 de escritura); 2 uso (`--full` con `--since`, fecha inválida, `--since` con hueco); 3 transitorio, seguro reintentar (red, 429/5xx tras 4 intentos, dataset reemplazado durante la corrida, dataset vacío en `--full`).
- Salida: `batch_id=… mode=… rows=… files=… watermark_from=… watermark_to=… manifest=s3://pits-raw/…/manifest.json`. Errores en stderr como `error: …`; el token nunca se imprime.
- Limitaciones aceptadas (detalle en `05`): 412 ambiguo tras un reintento (D65); correcciones a TRMs ya cargadas no se capturan sin `--full` o `--since` (D66).

### Resueltos por D47 y D48 (2026-10-10)

- R1 (grano de `fx_rate`): D47, fecha única; el normalizer expande el rango de la TRM a una fila por día.
- R2 (entidad y grano del parque RUNT) y R3 (marcas validadas con flujo): D48, demanda solo con el parque RUNT `u3vn-bdcy` por clase/geografía; marca/modelo sintético, calibrado con investigación pública.
- Pregunta de dominio (¿parque RUNT por clase como único insumo de demanda?): respondida por Henry, ver D48.

### Decisiones D50 y D51 (2026-10-10)

- T1: derecho de petición a MinTransporte por parque por marca — descartado (D50); se trabaja con fuentes públicas y el sintético de D48.
- Investigación de fuentes de parque por marca: `docs/research/parque_por_marca.md`.
- D51: `vehicle_registration_stat` renombrada a `vehicle_fleet_snapshot` (stock, no flujo).

### Decisiones D52–D56 (2026-10-10, segunda ronda regional)

- D52: desglose sintético marca/línea calibrado con el parque activo de Boyacá (`em3d-hmim`) por clase, aplicado a RUNT `u3vn-bdcy` (corte OCTUBRE 2026) del segmento PARTICULAR. Ajusta D48: de matrículas (flujo) a parque regional (stock).
- D53: la marca es la dimensión primaria del desglose; la línea es secundaria y puede agruparse en `OTRAS`.
- D54: el servicio PÚBLICO (1.100.711 vehículos, corte OCTUBRE 2026) es un segmento de flotas aparte, con comprador `fleet_operator`; no recibe el desglose de D52/D55.
- D55: calibración multirregión con Boyacá y Risaralda (`x9pp-pcn5`), pooling de conteos por clase; `AUTECO` se reasigna a marca real por línea; lo no asignable queda `SIN ASIGNAR`.
- D56: fuera de la demanda: `OFICIAL` y ventas al gobierno; `NO REGISTRA` y `OTROS` quedan fuera del MVP. Las tres categorías se conservan en `vehicle_fleet_snapshot`. Las motos de domicilio se quedan en PARTICULAR.

### Investigación regional de parque por marca (segunda ronda, 2026-10-10)

Fuente: `research/parque_por_marca.md`, sección "Segunda ronda". Estado por región:

- Nacional: no encontrado. Ninguna fuente pública nacional con marca.
- Segunda fuente con marca encontrada: Risaralda `x9pp-pcn5` (datos 2026-07-06; "registrado", sin `servicio` ni `estado`). Se suma a Boyacá `em3d-hmim` (datos 2024-08-30; ACTIVO; casi solo PARTICULAR).
- Parcial: Floridablanca `g7i9-xkxz` (datos 2023-02-10; automóvil PUBLICO, HYUNDAI 68,4 %), AMCO Pereira `fvnt-frpb` (datos 2020-11-07; solo transporte público), Fusagasugá `aj2e-7jwg` (datos 2026-06-01; muestra de 48.636 filas).
- No encontrado: Bogotá; Medellín y Cali (parque sin marca); Bucaramanga; Atlántico `n4ic-hiug` (datos solo hasta 2022).
- Caldas `dkxf-ikd7` (datos 2020) y Barbosa `syiu-8mvf` (datos 2020, título 2018): no vigentes. La fecha "actualizado 2026" de la primera ronda era la de metadatos.
- Corte RUNT `u3vn-bdcy`: OCTUBRE 2026 (ACTIVO 22.613.691; INCONSISTENTE 41.349; total 22.655.040). El corte AGOSTO 2026 citado en `08` ya no existe en la fuente (ver §7).

### Spike de storage S3: SeaweedFS 4.48 (2026-10-10, rama `spike/seaweedfs`, mergeada a `main` en PR #9)

Detalle completo en `docs/spikes/seaweedfs.md`. Resultados:

- Imagen `chrislusf/seaweedfs:4.48` inspeccionada (entrypoint, `Cmd` = `mini`, sin variables AWS); un contenedor `server -s3` con `mem_limit` 512m, `GOMEMLIMIT` 400MiB, solo `127.0.0.1:8333`, healthcheck `/healthz`.
- Tests de contrato (boto3 1.43.111, path-style): 14/14 con `-m contract` y 30 offline, sin `xfail`. Cubren buckets, objetos, Unicode, re-subida, multipart de 128 MiB con hash, versioning, delete markers, Object Lock COMPLIANCE/GOVERNANCE y legal hold.
- Persistencia: objeto testigo legible tras `docker compose down` (sin `-v`) y `up -d`, con hash idéntico.
- Memoria del cgroup (`memory.peak`): 420,2 / 440,5 / 456,8 MiB en tres corridas no comparables (82–89 % de 512 MiB); sin OOM. Reposo ~130 MiB. Cliente con tracemalloc ~51,8 MB.
- Disco: +128 MiB con un objeto de 128 MiB; liberado al borrar el bucket.
- No probado: s3fs y dbt (solo boto3); identidades distintas de la admin (no se probó Object Lock con identidad sin bypass); validación a 768m (hecha en el paso 2, D63); VPS (Linux nativo).
- Limpieza pendiente: el volumen `pits_spike_seaweedfs_data` se conserva (borrarlo es decisión de Henry). El contenedor está apagado.

### Decisiones D57–D59 (2026-10-10, cuestionario)

- D57: storage SeaweedFS 4.48 (`server -s3`) reemplaza a MinIO; memoria M1 (`mem_limit` = `memswap_limit` 768m, `GOMEMLIMIT` 600MiB, no validado aún; validado y ajustado a 500MiB por D63, ver §3 "Fase 1, paso 2"); raw inmutable opción A (write-once por `batch_id` + versioning en el bucket raw).
- D58: marker `contract` excluido por defecto (`addopts`); CI sin tests de contrato hasta tener job con SeaweedFS.
- D59: la demanda y el desglose sintético usan solo `ACTIVO`; `INCONSISTENTE` (41.349) se conserva en `vehicle_fleet_snapshot` pero no entra en la demanda.

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

### Paso 2 — hecho (D60–D63, en PR)

Evidencia en §3. Pendientes técnicos heredados de D57 (no bloquean el paso 3):

- Validación en VPS OVH: requiere confirmación explícita de Henry (regla 10).
- Volumen `pits_spike_seaweedfs_data` conservado con datos de prueba: borrarlo (`docker volume rm`) es decisión de Henry.
- Disco C: 29 GB libres (`df -h /c` tras la medición del paso 2, 2026-10-10). Las mediciones son de Docker sobre WSL2; el VPS es Linux nativo.

### Paso 3 — hecho (D64–D67, en PR)

Evidencia y cómo reejecutar en §3. Se escribe cada página como `payload-NNNNN.json` con `IfNoneMatch="*"` (D62) y objetos ≤ 8 MiB con `put_object` secuencial (D65); no hay multipart ni `TransferConfig`. Medición de memoria con el criterio de D63: 3/3 corridas `-m contract` (26 tests; medidas antes de añadir los 2 últimos tests de contrato de TRM).

### Próximo paso — normalización TRM (D47) y replay desde raw

**Siguiente paso:** hito técnico aparte, sin implementar. Rama propia desde `main` tras el merge del PR del paso 3, con `/orquestar`.

- Entrada: el último batch committed de `superfinanciera_trm` (su `manifest.json` y sus `payload-NNNNN.json`), leído desde `pits-raw` sin volver a llamar a la API.
- Salida: `fx_rate` (`03_data_model.md` §26) con una fila por día calendario del rango `vigenciadesde`–`vigenciahasta` (D47). Fines de semana y festivos heredan la TRM vigente. Grano: `rate_date` + `currency_from` + `currency_to`.
- Monedas: Henry pidió "Solo COP y USD" (2026-10-10); no es regla del modelo hasta que exista una D nueva aprobada (ver §7).
- Dedupe: por `rate_date`, con el batch committed más reciente (D65). Reejecutar un batch no crea duplicados lógicos.
- Replay: reconstruir la salida completa desde el raw, sin tocar la fuente. El raw conserva el rango original (D47).
- Tests: unitarios de la expansión y del dedupe; replay sobre `MemoryRawStore`; validaciones de dominio (§7).

Contexto del storage (paso 2): MinIO comunitario ya no se distribuye (repo `minio/minio` archivado 2026-04-25, imágenes `minio/minio` y `minio/mc` en 404 en Docker Hub, CVE altos sin parche libre, p. ej. CVE-2026-41145, GHSA-hv4r-mvr4-25vw); se usa SeaweedFS. `04_infra.md` §8.1 guarda `manifest.json` junto al payload en el storage, así que Postgres no es requisito del manifest.

### Pasos siguientes

3. (Hecho en el paso 3, D64 y D65.) Extractor SODA de TRM: paginación con `$order`, reintentos, token opcional (`X-App-Token`, desde variable de entorno). Escribe cada página en `pits-raw` (SeaweedFS, D57) con la key de D61: `superfinanciera_trm/extraction_date=YYYY-MM-DD/batch_id=<uuid>/payload-NNNNN.json`, con escritura condicional `IfNoneMatch="*"` (D62).
4. (Hecho en el paso 3, D65.) Manifest v1 (`manifest.json`, escrito al final como commit marker) con ID del dataset, atribución y licencia. Mapeo a `03_data_model.md` §3: `ingestion_batch_id` = `batch_id`; `ingested_at` = `finished_at`; `raw_object_path` = `s3://pits-raw/<files[].key>`; `record_hash` = `files[].sha256` (por archivo). `source_record_id` no aplica: la TRM no trae ID de registro; la llave natural es `vigenciadesde`.
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
- Rate limit sin token: número exacto no encontrado en la documentación. Registrar un token y manejar reintentos con backoff (reintentos implementados en D64; token opcional).
- Paginar siempre con `$order=vigenciadesde` (o `:id`).
- Tope por petición: 50.000 es el límite documentado para Socrata API 2.0; 08 no verificó qué versión sirve datos.gov.co. Con 8.360 filas cabría en una petición, pero se pagina para demostrar el patrón.

### Entregable de Fase 1 (criterios de salida)

- Llamada reproducible, raw payload preservado, batch ID, schema validado, idempotencia, manejo de errores, tests unitarios y documentación de cómo reejecutar un batch.

## 6. Entrada a Fase 1

Condición de entrada cumplida (D46, `08_market_research.md` Ficha 2). Entregable: ver §5.

## 7. Bloqueos y pendientes

- Pendiente (Henry): en su `.env` local, `POSTGRES_HOST_PORT=5433` si no lo puso (D60; 5432 suele estar ocupado por Postgres nativo de Windows).
- Pendiente (Henry): la auditoría semanal (`.github/workflows/claude-recurrente.yml`, D44) no funciona. El `workflow_dispatch` del PR #6 (run 38072914197, 2026-10-10) pasó checkout, setup-uv y `uv sync --locked --no-install-project`, pero falló en `anthropics/claude-code-action@v1`: "Claude Code is not installed on this repository". Acción (Henry): instalar la GitHub App https://github.com/apps/claude en el repo, confirmar el secret `CLAUDE_CODE_OAUTH_TOKEN` y relanzar con `gh workflow run claude-recurrente.yml`.
- Pendiente (Henry): borrar o conservar el volumen `pits_spike_seaweedfs_data` (con datos de prueba). Borrarlo es destructivo: no se ejecutó.
- Pendiente técnico: s3fs y dbt no probados contra SeaweedFS (entran con el primer consumidor). La validación de memoria se hizo con GOMEMLIMIT 500MiB (D63).
- Aprobado como D67 (2026-10-10): en Fase 3, las credenciales de ingesta del raw no tendrán `s3:DeleteObject`. Pendiente técnico de Fase 3: aplicarlo y probarlo.
- Riesgo abierto (D65): 412 ambiguo. Si un `put_object` se guarda pero se pierde la respuesta, el reintento recibe 412 y la corrida sale con exit 1 aunque el objeto sea propio. Limitación aceptada; caso en `07` (lección 83).
- Riesgo abierto: corridas concurrentes sin lock. Dos corridas a la vez crean dos batches; ambos pueden quedar committed. El watermark sale del batch con `finished_at` más reciente dentro de la partición `extraction_date` más nueva.
- Riesgo abierto: posible truncamiento. La paginación termina cuando `len(rows) < $limit`; si el servidor limita `$limit` por debajo de 1000, un batch incompleto podría quedar committed como válido. Falta una guarda contra el total de la API.
- Riesgo abierto: huérfanos sin inventario. Los batches sin `manifest.json` (corridas abortadas) se acumulan en `pits-raw`; los lectores los ignoran, pero no hay listado ni limpieza.
- Riesgo abierto: credenciales admin de SeaweedFS en la ingesta hasta Fase 3 (D67).
- Riesgo abierto: token sobre http. El default de `SODA_BASE_URL` es https; si se configura http, `X-App-Token` viaja sin cifrar.
- Riesgo abierto (D65): un manifest corrupto bloquea las corridas incremental y `--since` (exit 1); `--full` no lee manifests previos. Runbook: con D67 solo un administrador puede corregirlo.
- Pendiente de dominio, normalizer (paso 5 siguiente): validaciones de dominio no definidas, por ejemplo rangos con `vigenciahasta` anterior a `vigenciadesde` o rangos solapados. Definir con Henry antes de implementar.
- Pendiente de dominio: "Solo COP y USD" (Henry, 2026-10-10) aplica al normalizer. No está escrito en `03_data_model.md` §26; si es una regla del modelo, requiere una D nueva aprobada antes de implementar (regla 4).
- Pendiente de Fase 4 (DAG): Henry pidió la "Tasa promedio a las 10:00 AM CST". Aclarar antes de fijar el horario: CST es UTC-6 en sentido literal, y la hora de Colombia es UTC-5 todo el año. Además, EE. UU. central usa CDT (UTC-5) hasta el 1 de noviembre de 2026, así que "10:00 CST" puede significar 15:00 UTC (CDT) o 16:00 UTC (CST literal). El dataset se reemplaza a ~23:05 UTC (D66).
- Pendiente técnico: el spike corrió sobre Docker/WSL2 con C: al 95 % (26 GB libres en el spike; 29 GB tras el paso 2); validar en VPS requiere confirmación explícita de Henry (regla 10).
- Pendiente (Henry): KEK de SSE-S3 en texto plano en el filer (el log avisa si falta `s3.sse.kek.passphrase`; cifrado en reposo no habilitado): decidir antes del VPS.
- Pendiente (Henry), método de pooling de D55: suma de conteos u otra ponderación (`05` §F, punto 5). La interpretación aplicada está sujeta al PR.
- Pendiente (Henry), líneas sin asignar: en Boyacá, AUTECO deja 8,6 % sin marca real (503 de 5.862 filas, incluye PLUS con 75). PLATINO (Risaralda) no está verificado; ACTIVE 110 y LEGEND quedarían sin asignar.
- Pendiente (Henry), desglose por marca del segmento público: sin calibración aprobada (D54). Floridablanca (2023) y AMCO (2020) son muestras viejas o de un solo tipo de servicio.
- Pendiente (docs): `08` cita el corte AGOSTO 2026 de `u3vn-bdcy`, que ya no existe en la fuente (corte OCTUBRE 2026). Corregir la cita por PR; no cambia métricas.
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

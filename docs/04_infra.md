# 04 — Infraestructura y operación

Última actualización: 2026-10-13
Estado: v12 — Endurecimiento y optimización (D104–D111, 2026-10-13): identidades S3 y bucket policy en §8.1.1; sección de D111 (bytecode) y tiempos de arranque en §9; DAG `airflow_log_retention` en §10.1; secretos S3 por contenedor en §11, con el riesgo del filer y del master (sin autenticación desde la red Docker) en §11; retención de logs y escaneo de secretos en §13. Versión anterior: v11 — Fase 1b, parque RUNT (D96–D103, 2026-10-12/13): medición de memoria de Postgres y del scheduler con `runt_fleet_snapshot` (unchanged y force) en §9; segundo DAG y ventanas en §10.1; volúmenes y disco en §14. Versión anterior: v10 — orquestación con Airflow (D89–D95, hito Fase 4, 2026-10-12): medición de Airflow en §9, perfil `orchestration` y los dos archivos de compose en §10.1 (D95), secretos y riesgos en §11 y §13; nota de que dbt corre dentro del cgroup del scheduler. Versión anterior: v9 — dbt sobre `landing.fx_rate` (D85–D88, hito dbt, 2026-10-11): rol `pits_transformer`, matriz de privilegios, schemas `staging`, `intermediate` y `marts`, `profiles.yml`, `sslmode`, dependencias y tamaño de `.venv` en §8.3 y §8.4; §9 y §11 actualizados. Antes: v8 — PostgreSQL del warehouse implementado en §8.3 (base `pits_warehouse`, schemas `landing` y `ops`, roles de mínimo privilegio, conexión solo loopback; D79–D82); medición de memoria de Postgres y cambios de `scripts/measure_storage_memory.sh` en §9; notas de roles, `sslmode` y log en §11 y §13 (2026-10-11). Antes: v7 — zona normalized `pits-normalized` en §8.2 (D74, D75, D76); sin cambios en `docker-compose.yml`. Antes: v6 — nota de separación OLTP/warehouse en §7 y §8.3 (D70); sin cambios en `docker-compose.yml`. Antes: v5 — perfil `core` implementado en `docker-compose.yml` (D60–D63); §8.1 con el contrato del batch raw de la ingesta (D65, paso 3 de Fase 1).

## 1. Objetivo

Definir una infraestructura suficientemente realista para aprender despliegue y operación de pipelines sin convertir el proyecto en un ejercicio de administración de servidores.

Principios:

- desarrollo local primero;
- producción aislada en el VPS;
- datos persistentes fuera del ciclo de vida del contenedor;
- límites de recursos;
- secretos fuera del repositorio;
- backups verificables;
- healthchecks y logs;
- servicios expuestos públicamente solo cuando sea necesario.

## 2. Servidor de producción disponible

| Atributo | Valor observado |
|---|---|
| Proveedor | OVH |
| Modelo | VPS-2 2026 |
| vCores | 6 |
| RAM | 12 GB nominales; ~11 GiB visibles por el sistema |
| Disco | 100 GB nominales; ~96 GB utilizables |
| Swap | 4 GiB |
| Panel | Coolify |

## 3. Desarrollo local

Entorno actual:

- Windows;
- proyectos en `C:\dev`;
- Docker Compose para servicios locales;
- Git como control de versiones;
- VPS reservado para producción.

Objetivo de reproducibilidad:

```bash
docker compose up -d
```

debe levantar las dependencias principales del proyecto localmente, acompañado por comandos explícitos para inicializar seeds, base de datos y pipelines.

## 4. Consumo medido del VPS — 2026-10-03

Comandos usados:

- `free -h`
- `df -h /`
- `uptime`
- `docker stats --no-stream`
- `docker system df`

| Recurso | Uso observado | Disponible / referencia |
|---|---:|---:|
| RAM | 3.3 GiB usados | 8.1 GiB `available` |
| Swap | 41 MiB | 4.0 GiB |
| Disco | 23 GB usados | 74 GB disponibles |
| Load average 1/5/15 min | 0.93 / 0.64 / 0.65 | Sobre 6 vCores |

Docker observado:

- imágenes: ~7.2 GB;
- volúmenes: ~2.3 GB;
- build cache: ~346 MB reclamables.

## 5. Servicios existentes observados

| Servicio | RAM observada aproximada | Nota |
|---|---:|---|
| Metabase | 1.06 GiB | Stack existente; candidato a reutilizar |
| Coolify y servicios internos | ~0.8 GiB | App, DB, Redis, realtime, proxy, sentinel |
| Directus | 197 MiB | Otro proyecto/servicio existente |
| Contenedor no identificado `jogccgs...` | 154 MiB | Debe identificarse antes del deploy |
| Postgres de stack existente | 88 MiB | No asumir que debe reutilizarse |
| Odoo y otros | <35 MiB cada uno | Servicios adicionales |

## 6. Hallazgos operativos

### 6.1 Contenedores sin límite de memoria

En la medición original, los contenedores mostraban un límite equivalente a casi toda la RAM del host.

Riesgo: un proceso con fuga o consumo inesperado puede afectar servicios no relacionados.

Regla del proyecto:

- cada servicio nuevo tendrá límite de memoria explícito cuando el runtime lo permita;
- los límites se ajustarán con mediciones reales, no solo con estimaciones.

### 6.2 Sesiones abiertas

`uptime` reportó 7 usuarios/sesiones en la medición inicial.

Acción antes del despliegue:

```bash
who
w
```

Confirmar que las sesiones sean esperadas.

### 6.3 Contenedores no identificados

No desplegar nuevos servicios hasta documentar qué aplicaciones consumen los recursos actuales.

## 7. Arquitectura de servicios del proyecto

```text
Internet / sources
       |
       v
 ingestion jobs
       |
       v
+-------------------+
| SeaweedFS (D57)   |
| raw immutable     |
+-------------------+
       |
       v
 loaders / parsing
       |
       v
+-------------------+
| PostgreSQL        |
| source + warehouse|
+-------------------+
       |
       v
 dbt transformations
       |
       v
+-------------------+
| Metabase          |
+-------------------+

Airflow orchestrates ingestion -> load -> dbt -> quality checks.
```

Nota de separación OLTP/warehouse (D70). El diagrama anterior describe el warehouse y el pipeline; no incluye las apps. Las apps (marketplace y taller, `01_project_brief.md` §8.2) usan una base OLTP propia, separada del warehouse por base y rol. En local puede ser la misma instancia Postgres del perfil `core`, sabiendo que no aísla CPU ni I/O. Ninguna app escribe en el warehouse ni lo lee para operar. Los hechos operativos llegan al warehouse por una tabla outbox transaccional y su export al raw con manifest (entrega al menos una vez; dedupe por `event_id`). Un worker operacional maneja facturas electrónicas y webhooks; no es Airflow. Esta nota no cambia `docker-compose.yml`; el despliegue de las apps se decide en su hito.

## 8. Zonas de almacenamiento

### 8.1 SeaweedFS raw (D57)

Nota: MinIO fue reemplazado por SeaweedFS (D57; el repo comunitario de MinIO está archivado; ver `05_decisions_log.md`, D57). El principio de raw inmutable (D29) sigue: write-once por `batch_id` (`IfNoneMatch="*"`, D62) más versioning en el bucket raw.

Según D61, el bucket se llama `pits-raw` (se crea y verifica con `pits storage init`). La key no repite el prefijo `raw/`: `<source_system>/extraction_date=YYYY-MM-DD/batch_id=<uuid>/`, con `raw_object_path` = `s3://pits-raw/<key>`. La estructura de abajo describe la key dentro del bucket.

Objetivo: preservar la fuente original para replay y auditoría.

Estructura (D65, implementada en el paso 3 de Fase 1 para la TRM):

```text
<source_system>/
  extraction_date=YYYY-MM-DD/
    batch_id=<uuid>/
      payload-00000.json
      payload-00001.json
      ...
      payload-NNNNN.json
      manifest.json
```

- Cada página de la API es un objeto `payload-NNNNN.json` (NNNNN desde 00000), con los bytes de la respuesta tal cual. Una página por objeto; objetos ≤ 8 MiB con `put_object` secuencial, sin multipart.
- `manifest.json` se escribe al final, con `IfNoneMatch="*"`, y es el commit marker del batch: un batch sin manifest es huérfano y no es válido para los lectores.
- `extraction_date`, `started_at` y `finished_at` van en UTC; `batch_id` es un uuid4 por corrida.
- Para la TRM (`superfinanciera_trm`) cada payload tiene hasta 1000 filas (`PAGE_SIZE`), en el orden `vigenciadesde ASC, :id ASC`.

El formato del payload depende de la fuente:

- JSON (TRM: array de objetos, una página por objeto);
- NDJSON;
- CSV;
- archivo original descargado.

No convertir a parquet **antes** de conservar la representación original cuando hacerlo implique perder información.

#### 8.1.1 Identidades y bucket policy (D104, 2026-10-13)

Implementa D67 con la limitación de abajo. Ajusta D57, D62, D89, D95 y D102.

- `s3.json` se genera en cada `up` desde `.env` con `configs.content` de compose (Compose 2.23.1 o superior; local v5.5.1). Se monta en `/etc/seaweedfs/s3.json` y SeaweedFS arranca con `server -s3 -s3.config=…`, sin variables `AWS_*` (en 4.48 el admin de `AWS_*` convive con el s3.json y anulaba el aislamiento). El filer no persiste identidades (verificado). Ningún secreto queda versionado ni en el host.
- Identidades:
  - `pits_admin` (`S3_*`): Admin, Read, List, Tagging y Write. Solo para `storage init` y los tests contract.
  - `pits_writer` (`PITS_S3_WRITER_*`): Read, List y Write sobre raw y normalized. Lo usan extract y normalize.
  - `pits_reader` (`PITS_S3_READER_*`): Read y List sobre los dos buckets. Lo usan load y orphans.
  - No hay fallback al admin: si falta una variable, exit 1 con el nombre de la variable. `identity` es keyword-only y obligatorio.
  - Formato solo para writer y reader: key `[A-Za-z0-9]{16,128}`, secreto `[A-Za-z0-9_-]{32,128}`; las keys deben ser distintas de las otras identidades presentes. Al admin no se le valida el formato, para no romper el `.env` existente.
  - HeadBucket y GetBucketVersioning funcionan con Read y List, sin Admin (verificado).
- `storage init` aplica a `pits-raw` y `pits-normalized` una policy Deny con Principal `*`:
  - Sid `DenyObjectDelete`: DeleteObject y DeleteObjectVersion sobre `bucket/*`.
  - Sid `DenyVersioningChange`: PutBucketVersioning sobre `bucket`.
  - Orden: versioning primero, solo si no está Enabled; después la policy. Compara contra la policy existente de forma canónica, con todas las claves de cada statement; relee para verificar; imprime `policy=applied`.
  - LIMITACIÓN (aprobada por Henry el 2026-10-13, literal: "merged, acepto tus recomendaciones, sigue"; pendiente 1 de `06_status.md` §7, cerrado como aprobado): en SeaweedFS 4.48 el admin SÍ borra con DeleteObjects (multi-delete), aunque se agreguen `s3:DeleteObjects`, `s3:Delete*` o `s3:*` (5 variantes probadas en un probe efímero). DeleteObject y DeleteObjectVersion del admin dan 403. Writer, reader y anónimo están bloqueados en todo. Mitigación propuesta: el admin solo se usa en `storage init` y en los tests contract; test `xfail(strict=True)` `test_policy_denies_admin_multi_delete`.
  - Break-glass: quitar la policy con el admin (`delete_bucket_policy`), solo con confirmación de Henry.
- Airflow (D104(d)): el scheduler recibe solo writer y reader, más `S3_ENDPOINT_URL`, `S3_REGION`, `S3_RAW_BUCKET` y `S3_NORMALIZED_BUCKET` (lista explícita, sin glob `S3_*`).
- Contrato de los 403: `tests/contract/test_storage_identities_contract.py`. Las pruebas de borrado usan keys inexistentes bajo `_pits_probe/`; es no destructivo si las identidades están bien.
- Si cambia el JSON de identidades hay que recrear `seaweedfs`. Si cambian los nombres de los buckets: recrear `seaweedfs` y volver a correr `storage init`.

### 8.2 Normalized / parquet

Una representación parquet puede generarse después de validar y normalizar el payload raw.

Objetivos:

- tipado consistente;
- lectura eficiente;
- schema explícito;
- facilidad de carga a Postgres.

Zona normalized de la TRM (D74, D75, D76; hito TRM normalize, 2026-10-11):

- Bucket `pits-normalized` (`S3_NORMALIZED_BUCKET`, default `pits-normalized`), validado como D61, distinto del raw y sin prefijo `pits-contract-`. Versioning Enabled; sin Object Lock; sin lifecycle mientras no exista otra D (es derivable del raw; retención revisable).
- `pits storage init` crea y verifica el bucket de forma idempotente (estado Suspended = error). `pits normalize trm` solo verifica que exista y tenga versioning Enabled; nunca lo crea. `pits extract` también valida `S3_NORMALIZED_BUCKET` (configuración compartida, fail-fast).
- Key: `fx_rate/source_system=superfinanciera_trm/inputs_until=YYYY-MM-DD/fingerprint=<sha256>/fx_rate.csv` y `manifest.json`. `inputs_until` = `extraction_date` del último input; `fingerprint` = sha256 del JSON canónico {transform (name, rules_version), raw_bucket, inputs} (D76(e)).
- Formato: CSV UTF-8 sin BOM, LF, sin quoting. Parquet no se usa aún: se evalúa en Fase 3, porque el parquet embebe metadata del writer.
- Write-once (D62, D75): `put_once` ante 412 compara sha256 y longitud del objeto existente; igual = `already_identical`; distinto = conflicto permanente. Cada objeto (CSV y manifest) se sube con un solo `put_object` y debe ser ≤ 8 MiB (D65); si excede, error permanente. El CSV va primero y el manifest al final, como commit marker.
- Errores de verificación del bucket por BotoCoreError o 5xx: exit 3 (transitorio).
- Fuera de este hito: loader a Postgres, dbt y Airflow (Fase 3, `01` §10, D40).

### 8.3 PostgreSQL

Implementado en el hito loader fx_rate (D79–D82, 2026-10-11), en el perfil `core` local (volumen `pits_postgres_data`, D60):

- Base `pits_warehouse` (`PITS_WAREHOUSE_DB`). Schemas `landing` (carga; contiene `landing.fx_rate`) y `ops` (`schema_migration` y `load_run`), creados por `pits db migrate`.
- Schemas `staging`, `intermediate` y `marts`: los crea el bootstrap con dueño `pits_owner` (D86); dbt solo construye objetos dentro de ellos. Nomenclatura confirmada por el proyecto dbt (`transform/macros/generate_schema_name.sql` usa el schema tal cual).
- Roles de mínimo privilegio (D79): `pits_owner` NOLOGIN, dueño de la base y de los schemas; `pits_loader` (inserta y actualiza `landing.fx_rate`; inserta en `ops.load_run` y actualiza solo sus tres contadores; sin DDL ni TRUNCATE); `pits_reader` (solo SELECT en `landing` y `ops.load_run`, y SELECT en `marts`); `pits_transformer` (dbt, D86; matriz en §8.4). Ningún rol es superusuario. El superusuario de la imagen (`POSTGRES_USER`) se usa solo en `pits db migrate`.
- Contraseñas de loader, reader y transformer desde `.env` (`PITS_PG_LOADER_PASSWORD`, `PITS_PG_READER_PASSWORD` y `PITS_PG_TRANSFORMER_PASSWORD`, 16 caracteres o más). Se envían como verificador SCRAM-SHA-256 calculado en el cliente, y cada `pits db migrate` las vuelve a fijar desde `.env`.
- Conexión: solo loopback (`127.0.0.1`, `localhost`, `::1`) y puerto distinto de 5432 (default 5433). `sslmode=disable` se acepta solo en loopback. En el VPS requiere una decisión nueva (D nueva) antes de usarse, con cifrado de tránsito.
- Riesgo de logs: con `log_statement` = `ddl` o `all`, los `ALTER ROLE ... PASSWORD` del bootstrap quedan en el log del servidor con el verificador SCRAM (no con la contraseña en claro). La imagen usa el valor por defecto (`none`). No activar `ddl` o `all` sin revisar esto. Inferencia: un verificador filtrado permite probar contraseñas fuera de línea; la mitigación es la longitud mínima de 16 caracteres y no registrar DDL.

Separación OLTP/warehouse (D70): las apps no usan estos schemas para operar. Su persistencia transaccional es una base OLTP propia (`01_project_brief.md` §8.2), separada del warehouse por base y rol; en local puede compartir la instancia, pero no el aislamiento de recursos. El warehouse recibe los hechos por outbox y export al raw con manifest, nunca por escritura directa de las apps. Los usuarios de mínimo privilegio se definen en Fase 3 (D60, §11).

### 8.4 Rol `pits_transformer`, dbt y `profiles.yml` (D85–D88, hito dbt, 2026-10-11)

Matriz de privilegios (fuente: `bootstrap.py` y `migrations/0003_transformer_grants.sql`; "—" = sin privilegio):

| Objeto | `pits_owner` | `pits_loader` | `pits_reader` | `pits_transformer` |
|---|---|---|---|---|
| Base `pits_warehouse` | dueño | CONNECT, TEMPORARY | CONNECT | CONNECT |
| Schema `landing` | dueño | USAGE | USAGE | USAGE |
| `landing.fx_rate` | dueño | SELECT, INSERT, UPDATE, DELETE | SELECT | SELECT |
| Schema `ops` | dueño | USAGE | USAGE | USAGE |
| `ops.load_run` | dueño | SELECT, INSERT; UPDATE solo de los tres contadores | SELECT | SELECT |
| Schema `staging` | dueño | — | — (REVOKE) | USAGE, CREATE |
| Schema `intermediate` | dueño | — | — (REVOKE) | USAGE, CREATE |
| Schema `marts` | dueño | — | USAGE; SELECT en tablas (default privileges) | USAGE, CREATE |
| Schema `public` | — | — | — (REVOKE a PUBLIC) | sin CREATE |

Reglas de uso:

- Rol `pits_transformer` LOGIN con `NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS`. Contraseña en `PITS_PG_TRANSFORMER_PASSWORD` (16 caracteres o más). `pits db migrate` la exige: un `.env` sin esa variable hace fallar la migración, aunque el loader y el reader estén completos.
- `transform/profiles.yml` solo usa `env_var`, sin secretos: `host` = `PITS_PG_HOST` (default `127.0.0.1`), `port` = `POSTGRES_HOST_PORT` (default 5433), `dbname` = `PITS_WAREHOUSE_DB`, `user` y `password` del transformer, `sslmode: disable`, `threads: 1`. El wrapper `pits transform` inyecta estos valores desde los settings validados (D88), así que dbt conecta igual que el preflight.
- `sslmode`: dbt usa `prefer` por defecto; el proyecto fija `disable` de forma explícita, y solo es aceptable en loopback, igual que en §8.3. En el VPS hace falta una D nueva con cifrado de tránsito.
- Dependencias (`pyproject.toml`, grupo `transform`): `dbt-core>=1.12,<1.13` y `dbt-postgres>=1.11,<1.12`; `default-groups = ["dev", "transform"]`; `exclude-dependencies = ["dbt-core-experimental-parser"]` (D85). `dbt --version` consulta PyPI (conexión saliente, no telemetría); la telemetría está desactivada en `dbt_project.yml` y con `DO_NOT_TRACK=1` en el proceso hijo.
- Tamaño del entorno (cifras del orquestador, S1): `.venv` pasó de 464M a 203M con la exclusión de `dbt-core-experimental-parser`.
- Salidas de dbt: `transform/target/` y `transform/logs/` (ignoradas por git). En la corrida real del 2026-10-11 ningún archivo de esas carpetas contenía la contraseña del transformer (`06_status.md` §3).
- Zona horaria: la sesión de dbt usa la del servidor, mientras el preflight de `pits` fija UTC. Los modelos actuales no castean timestamps a fecha; si se añade uno, fijar la zona o documentarlo.
- CI (`.github/workflows/ci.yml`) ejecuta solo `uv run pits transform parse`, que no usa credenciales ni conecta. `dbt build` en CI sigue en Fase 5 (D40).

## 9. Componentes nuevos y presupuesto de capacidad

Los rangos siguientes son **presupuesto de planificación**, no garantías de consumo.

| Componente | Rango inicial de planificación | Acción |
|---|---:|---|
| Airflow + metadata DB (D89, D93) | Medido el 2026-10-12; reemplaza el estimado previo de 2,5–4 GB: scheduler 581,9 MiB (límite 2 GiB), apiserver 242,5 MiB (límite 1 GiB), dag-processor 254,6 MiB (límite 768 MiB). La metadata vive en `pits-postgres` (66,1 MiB, instancia compartida; ver medición abajo). Fuente: `06_status.md` §3 | Criterio análogo a D63 (max(`memory.peak`) < 85 % del límite): CRITERIO OK. Pendiente: medir una corrida con extract full (no medida) |
| PostgreSQL warehouse | 0.5–1.5 GB | Ajustar conexiones/cache al VPS |
| SeaweedFS 768m (D57; `GOMEMLIMIT` 500MiB, D63) | 0.75 GiB ≈ 0.8 GB (`mem_limit` 768 MiB; pico medido 513–538 MiB con GOMEMLIMIT 500MiB; con 600MiB, 620–661 MiB) | Criterio: max(`memory.peak`) < 85 % del límite; vigilar memoria y disco |
| PostgreSQL local perfil `core` (D60) | 1 GiB (`mem_limit` = `memswap_limit` 1g; lectura puntual de `memory.current` = 130818048 B (~125 MiB) tras el primer up, 2026-10-10; sin log guardado) | Locale `C.UTF-8` builtin; puerto host 5433 por defecto |
| dbt runner (`pits transform`, D88) | Burst; no residente. Pico de Postgres con carga dbt (`pytest -m pg`): máx. 77,01 MiB, 7,5 % de 1 GiB (2026-10-11, `06_status.md` §3). Proceso dbt del host sin medir | Ejecutar como job; no es servicio |
| Redpanda | ~1 GB o más | Solo fase opcional y después de nueva medición |

Medición del pico de memoria de Postgres (hito loader fx_rate, 2026-10-11; `scripts/measure_storage_memory.sh` con `C=pits-postgres`, `EXPECTED_LIMIT=1073741824`, `PEAK_LIMIT=912680550`, `EXPECTED_GOMEMLIMIT` vacío y carga `pytest -m pg -q`; fuente: log de la sesión, no versionado, citado en `06_status.md` §3):

- 3/3 corridas con rc=0, `memory.events` con `oom=0` y `oom_kill=0`, `OOMKilled=false`. El script reinicia el contenedor antes de cada corrida; `RestartCount=0` tras cada una.
- `memory.peak`: 120229888, 120696832 y 70983680 B (114,66, 115,11 y 67,70 MiB). Máximo 115,11 MiB = 11,2 % de 1 GiB, por debajo del 85 % (912680550 B).
- GOMEMLIMIT no aplica a Postgres (no es Go): `EXPECTED_GOMEMLIMIT` vacío omite esa validación.
- Tamaño de datos no medido en esta corrida: se ejecutó sin `DATA_DIR` y el default `/data` no existe en Postgres (el log muestra `du: cannot access '/data'`). Para medirlo, `DATA_DIR=/var/lib/postgresql/data`; el script ya lo soporta (commit 9f523f8, según el coordinador).
- Script `scripts/measure_storage_memory.sh` (código actual): `EXPECTED_GOMEMLIMIT` usa `${EXPECTED_GOMEMLIMIT-500MiB}`, así que vacío omite la validación de GOMEMLIMIT; `DATA_DIR` usa `${DATA_DIR-/data}`, así que vacío omite el tamaño de datos. Los defaults no cambian para SeaweedFS.

Medición de Airflow (hito Fase 4, 2026-10-12; 3 corridas por contenedor, reportada por el orquestador; log no versionado, citado en `06_status.md` §3). Carga: `trm_daily` con extract incremental. Resultado: rc=0 en todas, sin OOM ni reinicios, `CRITERIO OK`.

- `memory.peak` del scheduler: 603742208, 610160640 y 569274368 B (máximo 581,9 MiB, 28 % de 2 GiB).
- `memory.peak` del apiserver: 254160896, 253865984 y 254291968 B (242,5 MiB, 24 % de 1 GiB).
- `memory.peak` del dag-processor: 266727424, 266993664 y 266350592 B (254,6 MiB, 33 % de 768 MiB).
- `memory.peak` de `pits-postgres`: 69353472, 61849600 y 59973632 B (66,1 MiB, 6,5 % de 1 GiB).
- dbt corre dentro del cgroup del scheduler (subproceso de la tarea), así que su consumo entra en el pico de ese contenedor. No se midió el proceso dbt por separado ni una corrida con extract full.

Medición del hito Fase 1b (parque RUNT, D96–D103; 2026-10-12/13; criterio D63/D89: max(`memory.peak`) < 85 % del límite; cifras reportadas por el orquestador, logs no versionados, citadas en `06_status.md` §3):

- `pits-postgres` con los tests `pg` del loader y el e2e: 3/3 corridas, picos 113709056, 115159040 y 114356224 B; máximo 109,8 MiB (10,7 % de 1 GiB). Sin OOM.
- Scheduler (límite 2 GiB) con `runt_fleet_snapshot` en modo `unchanged`: 3/3 corridas, máximo 640401408 B (610,7 MiB, 30 %). Sin OOM.
- Scheduler con `force` (ruta pesada, descargar y normalizar todo): 1 corrida, pico 642220032 B (612,5 MiB, 30 %). Una sola corrida, por decisión de Henry (2026-10-13, respuesta "2"); no es una distribución de tres corridas.
- El proceso dbt sigue sin medirse por separado: corre dentro del cgroup del scheduler, como en la medición de Airflow.
- Normalize del RUNT (cifras de la corrida real, 2026-10-12): RSS 154,8 MiB con tracemalloc de 75,6 MiB; load del cliente con RSS 87,4 MiB. Son mediciones del proceso `pits`, no del contenedor.

Medición del hito Endurecimiento y optimización (D111, 2026-10-13; reportada por el orquestador, no reejecutada por el documentador):

- Imagen `pits-airflow` con `UV_COMPILE_BYTECODE=1` en los dos `uv sync` del Dockerfile: 1.380.302.774 → 1.448.939.918 B (+68,6 MB).
- `pits version`: 1,391 → 0,714 s (−48,7 %), mediana de 5 arranques en frío. `import dbt.cli.main`: 3,438 → 1,828 s (−46,8 %). El revisor, con medidas propias: −53 % y −47 %.
- Los `.pyc` son de root y de solo lectura, compatibles con D89; con UID 1234:0 funciona. `/opt/pits/src` (instalación editable) no se compila; compilarlo requiere una D nueva.
- Imágenes: antes `sha256:67758b6cb6b5…` (sin etiqueta). Imagen que corre, verificada por el orquestador el 2026-10-13: `pits-airflow:dev` = `sha256:2092eac28e2d547f814e6f25cb8af939405c2767a474252df0e91af61505a5ad` (1.448.939.918 B), con los 3 contenedores de Airflow recreados a las ~06:15 UTC, healthy y sin import errors. Viene del rebuild de S7, que solo cambió un comentario; sus capas son idénticas a `be227ecc6fa0d12f8d25b2ed49434c6e5fd8c834a23ad608dcee604202de54ae`, que conserva la etiqueta `:bytecode` porque la referencia el contenedor one-shot `airflow-init`, ya detenido.

Medición de dbt (D110, 2026-10-13): mediana de 3 builds = 9,500 s (< 10 s, regla fijada antes de medir); sin cambios. Los tiempos son 7,727 / 9,500 / 18,123 s; el máximo es 2,3 veces el mínimo, por lo que 3 corridas son frágiles (ver D110).

No desplegar Redpanda mientras el stack base no tenga margen medido suficiente.

## 10. Estrategia de despliegue

### 10.1 Local

Docker Compose con perfiles cuando ayude:

- `core`: Postgres + SeaweedFS (D57), definido en `docker-compose.yml` (D60–D63). SeaweedFS publica `127.0.0.1:8333`; Postgres publica `127.0.0.1:5433` por defecto (`POSTGRES_HOST_PORT`; 5432 suele estar ocupado en Windows). Bucket `pits-raw` creado con `pits storage init` (D61). `docker-compose.spike.yml` también usa 8333: no levantarlo a la vez que `core`;
- `orchestration`: Airflow 3.3.2 con LocalExecutor (D89, D95), en `docker-compose.orchestration.yml`: `airflow-init` (`db migrate` y `pools set`), `apiserver` (solo `127.0.0.1:8080`), `scheduler` (parallelism 2, con dbt dentro de su cgroup) y `dag-processor`; sin triggerer. `docker-compose.yml` conserva solo el perfil `core`, sin variables nuevas obligatorias (D95). Uso: `docker compose -f docker-compose.yml -f docker-compose.orchestration.yml --profile core --profile orchestration ...`; con `COMPOSE_FILE`, el separador es `;` en Windows y `:` en Linux (el de Linux no se probó). Metadata DB en la misma instancia Postgres, base y rol `airflow_meta` (D93). Imagen `pits-airflow` (D89; `pits-airflow:dev` de 1380040724 B, 1,38 GB; `docker image inspect`, build del 2026-10-12 a las 20:06:39 UTC);
- DAGs (D92, D102): `trm_daily` a las 10:00 America/Bogota (15:00 UTC) y `runt_fleet_snapshot` a las 11:00 America/Bogota (16:00 UTC), diarios, `max_active_runs=1`. Ambos usan el pool `pits_warehouse` de 1 slot en load, build y freshness (D90), y `runt_fleet_snapshot` tiene `dagrun_timeout` de 120 min (D102). Las pruebas de integración `-m airflow` se corren lejos de las 15:00 y las 16:00 UTC. Su param `force` (solo bool) pasa `--force` al extractor; `--repair` y `--fingerprint` siguen solo por CLI manual;
- `airflow_log_retention` (D109): diario a las 03:00 America/Bogota (08:00 UTC), catchup False, `max_active_runs` 1, sin pool, `execution_timeout` 10 min y retries 0. Borra los `*.log` regulares con más de 30 días bajo `/opt/airflow/logs` (lstat, sin seguir symlinks), luego los directorios vacíos de abajo hacia arriba, nunca la raíz. No limpia la metadata DB. Corrida real (2026-10-13): `deleted_files=0 freed_bytes=0 removed_dirs=0`. Tres DAGs en total;
- `bi`: Metabase opcional local;
- `streaming`: Redpanda solo fase futura.

### 10.2 Producción

Coolify administra los servicios desplegados en el VPS.

Reglas:

- volúmenes persistentes explícitos;
- healthcheck por servicio;
- restart policy razonable;
- límites de memoria;
- credenciales mediante secrets/env vars del entorno;
- no guardar `.env` real en Git;
- no exponer Postgres/SeaweedFS (D57) directamente a internet sin una necesidad documentada.

## 11. Red y acceso

Mínimos:

- HTTPS para interfaces públicas;
- paneles administrativos restringidos;
- bases de datos accesibles solo desde redes/servicios necesarios;
- credenciales únicas por servicio;
- principle of least privilege cuando se creen usuarios DB;
- evitar usar el usuario administrador para pipelines rutinarios.

Implementado en Fase 3 (D79): el loader usa `pits_loader` y las consultas usan `pits_reader`; el administrador solo se usa en `pits db migrate`. Ambos roles se crean sin superusuario, sin CREATEDB, sin CREATEROLE, sin herencia y sin BYPASSRLS. Postgres sigue publicado solo en `127.0.0.1` (D60). Las credenciales de ingesta del raw siguen con permisos admin hasta aplicar D67. CERRADO (D104, 2026-10-13): la ingesta usa la identidad `pits_writer` y no el admin; D67 queda implementada por D104, con la limitación de DeleteObjects del admin (pendiente 1 de `06_status.md` §7, aprobada por Henry el 2026-10-13). dbt usa `pits_transformer` (D86): lee `landing` y escribe solo en sus schemas. CI no tiene credenciales de warehouse: ejecuta `pits transform parse`, que no conecta.

Airflow (D89, D93, D95): el scheduler y el apiserver reciben sus secretos (`AIRFLOW_FERNET_KEY`, `AIRFLOW_API_JWT_SECRET`, `AIRFLOW_API_SECRET_KEY` y `AIRFLOW_METADB_PASSWORD` para la metadata); el dag-processor recibe `AIRFLOW_FERNET_KEY`, `AIRFLOW_API_JWT_SECRET` y `AIRFLOW_METADB_PASSWORD`; la contraseña del admin de la UI sale de `AIRFLOW_ADMIN_PASSWORD`, que se escribe en el archivo de contraseñas con umask 077 antes del exec. Ningún contenedor recibe `POSTGRES_PASSWORD` ni la contraseña del reader; solo el scheduler recibe las credenciales de pits. La metadata usa el rol `airflow_meta` (D93), sin CONNECT a `pits_warehouse`. La UI publica solo `127.0.0.1:8080` y usa SimpleAuthManager (contraseña en texto plano en su archivo; solo loopback). Riesgos abiertos: el proceso de la tarea hereda el entorno del scheduler (metadata, Fernet, JWT); el subproceso de `pits` no lo hereda (allow-list, D92). Credenciales S3 admin en Airflow hasta D67 (P6, aceptadas solo en local). CERRADO (D104(d), 2026-10-13): el scheduler ya no recibe credenciales admin de S3. Secretos S3 (D104(d)): el scheduler recibe `pits_writer` y `pits_reader` en `secret_env`, más `S3_ENDPOINT_URL`, `S3_REGION`, `S3_RAW_BUCKET` y `S3_NORMALIZED_BUCKET` como variables no secretas (lista explícita, sin glob `S3_*`). apiserver y dag-processor no reciben ninguna variable S3. Ya no hay credenciales admin de S3 en Airflow; el admin solo se usa en `storage init` y en los tests contract (D104).

Riesgo abierto (pendiente 2 de `06_status.md` §7; DIFERIDO por decisión de Henry, 2026-10-13; requiere D propia antes del VPS): el filer (:8888) y el master (:9333) de SeaweedFS responden sin autenticación desde la red Docker `pits_default` (verificado desde el scheduler). Por la API HTTP del filer se puede borrar sin pasar por las identidades ni por la policy. Desde el host no son accesibles. La mitigación prevista es una D propia (JWT en `security.toml` o red separada) antes de cualquier despliegue en el VPS. No hay D aprobada para este riesgo.

## 12. Persistencia y backups

Datos que requieren volumen persistente:

- PostgreSQL;
- metadata DB de Airflow si está separada;
- SeaweedFS (D57);
- configuración persistente necesaria de BI.

Plan mínimo antes de considerar producción “cerrada”:

1. backup de PostgreSQL;
2. backup o replicación de objetos críticos de SeaweedFS (D57);
3. política de retención;
4. prueba de restauración documentada.

Un backup que nunca se ha restaurado no se considera validado.

## 13. Logs y observabilidad mínima

Notas del loader fx_rate (D82, 2026-10-11): `pits load fx-rate` y `pits db migrate` imprimen una línea de resultado (`outcome=…` o `database=… applied=… skipped=…`) y los errores con `str(exc)`; nunca imprimen conninfo ni contraseñas. Las excepciones no tipadas salen con traceback y exit 1. El traceback no muestra variables locales, pero no se verificó que el encadenamiento de excepciones (`__context__`) de una excepción no tipada nunca contenga el pgconn con la contraseña. Revisar antes de compartir un log de esas corridas. El riesgo del verificador SCRAM en el log del servidor está en §8.3.

Notas de Airflow (D89 y D92, 2026-10-12): los logs de Airflow viven en el volumen `pits_airflow_logs` y crecen sin limpieza. CERRADO (D109, 2026-10-13): el DAG `airflow_log_retention` borra los `*.log` regulares de más de 30 días y los directorios vacíos; no limpia la metadata DB (§10.1). Escaneo de secretos (D104, 2026-10-13): la suite `-m airflow` rápida (7 passed) incluye el escaneo con writer y reader requeridos. Los secretos se enmascaran con `mask_secret` de `airflow.sdk.log`. Escaneo de secretos de los logs de la corrida medida: 0 apariciones de las variables (`SODA_APP_TOKEN` vacío). El escaneo se hizo desde el scheduler y no incluye `AIRFLOW_ADMIN_PASSWORD` (solo lo tiene el apiserver). Healthchecks: apiserver `/api/v2/monitor/health`; scheduler con HTTP en el puerto 8974; dag-processor con `airflow jobs check`. Exit codes del DAG: 0 éxito; 3 reintenta (retries=3, retry_delay 5 min, máximo 30 min); cualquier otro, incluidos -9 y las señales, falla sin reintento (D92).

Cada pipeline debe registrar al menos:

- `run_id` / `batch_id`;
- fuente;
- hora de inicio/fin;
- filas/objetos leídos;
- filas cargadas;
- filas rechazadas;
- resultado de tests;
- excepción cuando falle.

Métricas iniciales a observar:

- duración de DAGs;
- fallas/retries;
- freshness;
- volumen por ingesta;
- uso de disco;
- uso de memoria del host y servicios principales.

No es obligatorio incorporar una plataforma dedicada de observabilidad en el MVP; primero se instrumentan logs y métricas útiles.

## 14. Gestión de disco

El raw zone crecerá con cada ejecución. Debe existir desde el inicio una política de particionado y una revisión periódica de:

```bash
df -h
docker system df
```

Antes de borrar raw data para liberar espacio, documentar qué capacidad de replay se pierde.

Medición del hito Fase 1b (2026-10-12/13; reportada por el orquestador):

- Disco C: de 37 a 44 GB libres tras las corridas y las mediciones.
- Volúmenes Docker: `pits_postgres_data` 459,5 MB; `pits_seaweedfs_data` 183,3 MB; `pits_airflow_logs` 4,4 MB.
- Build cache de Docker: 2,8 GB, de los que 1,7 GB son recuperables. No se borró: requiere permiso de Henry. `PITS_IT_FORCE=1` (integración con `--force`) agrega unos 86 MB permanentes.
- Crecimiento permanente del RUNT: hoy hay 3 batches en `pits-raw` (unos 151 MB) y 3 artefactos en `pits-normalized` (unos 108 MB). Cada publicación nueva y cada `--force` agregan ambos. No hay lifecycle (D61, D74); la purga es decisión pendiente de Henry. No forzar corridas sin motivo.

## 15. Checklist previo al primer deploy

- [ ] Identificar todos los contenedores actuales del VPS.
- [ ] Confirmar sesiones activas esperadas.
- [ ] Definir puertos internos/externos.
- [ ] Crear secrets fuera del repositorio.
- [ ] Definir volúmenes persistentes.
- [ ] Configurar healthchecks.
- [ ] Aplicar límites de memoria.
- [ ] Configurar backup de Postgres.
- [ ] Definir backup/retención de SeaweedFS (D57).
- [ ] Ejecutar prueba de restauración.
- [ ] Medir RAM/disco después del deploy base.
- [ ] Documentar cómo hacer rollback.

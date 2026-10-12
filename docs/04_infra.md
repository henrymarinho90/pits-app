# 04 — Infraestructura y operación

Última actualización: 2026-10-12
Estado: v9 — dbt sobre `landing.fx_rate` (D85–D88, hito dbt, 2026-10-11): rol `pits_transformer`, matriz de privilegios, schemas `staging`, `intermediate` y `marts`, `profiles.yml`, `sslmode`, dependencias y tamaño de `.venv` en §8.3 y §8.4; §9 y §11 actualizados. Antes: v8 — PostgreSQL del warehouse implementado en §8.3 (base `pits_warehouse`, schemas `landing` y `ops`, roles de mínimo privilegio, conexión solo loopback; D79–D82); medición de memoria de Postgres y cambios de `scripts/measure_storage_memory.sh` en §9; notas de roles, `sslmode` y log en §11 y §13 (2026-10-11). Antes: v7 — zona normalized `pits-normalized` en §8.2 (D74, D75, D76); sin cambios en `docker-compose.yml`. Antes: v6 — nota de separación OLTP/warehouse en §7 y §8.3 (D70); sin cambios en `docker-compose.yml`. Antes: v5 — perfil `core` implementado en `docker-compose.yml` (D60–D63); §8.1 con el contrato del batch raw de la ingesta (D65, paso 3 de Fase 1).

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
| Airflow + metadata DB | 2.5–4 GB | Medir por proceso y ajustar |
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

No desplegar Redpanda mientras el stack base no tenga margen medido suficiente.

## 10. Estrategia de despliegue

### 10.1 Local

Docker Compose con perfiles cuando ayude:

- `core`: Postgres + SeaweedFS (D57), definido en `docker-compose.yml` (D60–D63). SeaweedFS publica `127.0.0.1:8333`; Postgres publica `127.0.0.1:5433` por defecto (`POSTGRES_HOST_PORT`; 5432 suele estar ocupado en Windows). Bucket `pits-raw` creado con `pits storage init` (D61). `docker-compose.spike.yml` también usa 8333: no levantarlo a la vez que `core`;
- `orchestration`: Airflow;
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

Implementado en Fase 3 (D79): el loader usa `pits_loader` y las consultas usan `pits_reader`; el administrador solo se usa en `pits db migrate`. Ambos roles se crean sin superusuario, sin CREATEDB, sin CREATEROLE, sin herencia y sin BYPASSRLS. Postgres sigue publicado solo en `127.0.0.1` (D60). Las credenciales de ingesta del raw siguen con permisos admin hasta aplicar D67. dbt usa `pits_transformer` (D86): lee `landing` y escribe solo en sus schemas. CI no tiene credenciales de warehouse: ejecuta `pits transform parse`, que no conecta.

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

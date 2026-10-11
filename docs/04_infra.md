# 04 — Infraestructura y operación

Última actualización: 2026-10-10
Estado: v5 — perfil `core` implementado en `docker-compose.yml` (D60–D63); arquitectura operativa revisada; §8.1 con el contrato del batch raw de la ingesta (D65, paso 3 de Fase 1).

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

### 8.3 PostgreSQL

Separación lógica sugerida:

- `source` o schemas equivalentes para datos cargados;
- `staging` administrado por dbt;
- `intermediate`;
- `analytics` / marts.

La nomenclatura definitiva se decidirá al crear el proyecto dbt.

## 9. Componentes nuevos y presupuesto de capacidad

Los rangos siguientes son **presupuesto de planificación**, no garantías de consumo.

| Componente | Rango inicial de planificación | Acción |
|---|---:|---|
| Airflow + metadata DB | 2.5–4 GB | Medir por proceso y ajustar |
| PostgreSQL warehouse | 0.5–1.5 GB | Ajustar conexiones/cache al VPS |
| SeaweedFS 768m (D57; `GOMEMLIMIT` 500MiB, D63) | 0.75 GiB ≈ 0.8 GB (`mem_limit` 768 MiB; pico medido 513–538 MiB con GOMEMLIMIT 500MiB; con 600MiB, 620–661 MiB) | Criterio: max(`memory.peak`) < 85 % del límite; vigilar memoria y disco |
| PostgreSQL local perfil `core` (D60) | 1 GiB (`mem_limit` = `memswap_limit` 1g; lectura puntual de `memory.current` = 130818048 B (~125 MiB) tras el primer up, 2026-10-10; sin log guardado) | Locale `C.UTF-8` builtin; puerto host 5433 por defecto |
| dbt runner | Burst; no siempre residente | Ejecutar como job cuando sea posible |
| Redpanda | ~1 GB o más | Solo fase opcional y después de nueva medición |

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

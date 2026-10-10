# Spike: SeaweedFS 4.48 como storage S3 local

## Objetivo

Evaluar SeaweedFS 4.48 como storage S3 local tras el archivo de MinIO comunitario.
La decisión de storage será D57 y la de markers de tests de contrato D58 (D52–D56 las ocupa otra tarea de dominio).

## Hipótesis

- SeaweedFS (`server -s3` o `mini`) expone una API S3 compatible con boto3/s3fs/dbt sin cambios de código.
- Una identidad S3 se puede crear solo con variables de entorno (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`), sin archivo de config.
- Existe un endpoint de salud usable en un healthcheck de Docker Compose.

## Inspección de la imagen

Imagen: `chrislusf/seaweedfs:4.48`
Digest: `chrislusf/seaweedfs@sha256:4e61d15fd35994cb1e43e1e553dff106794841fd9a99ade2fc8c8bfce4d7872d`
Motor: Docker 29.8.2.

```text
Entrypoint=["/entrypoint.sh"]  Cmd=["mini","-dir=/data"]
Env=["PATH=..."]  (sin variables AWS en la imagen)
ExposedPorts: 7333 8080 8333 8888 9333 18080 18888 19333
```

```text
$ docker run --rm chrislusf/seaweedfs:4.48 version
version 30GB 4.48 530be3e37 linux amd64
```

El entrypoint es un script sh: el primer argumento selecciona el modo
(`master|volume|server|mini|filer|s3|shell`, otro -> `weed $@`). Corre como root, hace
chown de /data y baja a usuario `seaweed` con su-exec. Activa `GODEBUG=fips140=on` por defecto (desactivable con `-e GODEBUG=fips140=off`, entrypoint.sh:4-5).
`server` antepone `-dir=/data -volume.max=0 -master.volumeSizeLimitMB=1024`;
`mini` antepone `-dir=/data` salvo que se pase `-dir`.

Herramientas: `/usr/bin/curl` (binario) y `/usr/bin/wget` (symlink a busybox).

`weed mini` existe (default Cmd de la imagen). Flags relevantes:

```text
-bucket string       comma-separated S3 bucket names to create on startup ... Falls back to S3_BUCKET env var.
-s3.config string    path to the S3 config file
-s3.port int         s3 server http listen port (default 8333)
-s3.iam              enable embedded IAM API on the same port (default true)
-s3.iam.readOnly     disable IAM write operations on this server (default true)
-s3.allowEmptyFolder deprecated, ignored. Empty folder cleanup is now automatic. (default true)   [server]
```

`weed s3 -h` (credenciales por entorno):

```text
Alternatively, you can use environment variables as fallback admin credentials:
AWS_ACCESS_KEY_ID=your_access_key AWS_SECRET_ACCESS_KEY=your_secret_key weed s3
Environment variables are only used when no S3 configuration file is provided
and no configuration is available from the filer.
```

Búsqueda de object lock / versioning en la ayuda (comando exacto, 0 líneas en los tres):

```text
$ for m in mini server s3; do docker run --rm --entrypoint weed chrislusf/seaweedfs:4.48 $m -h 2>&1 | grep -iwE 'lock|retention|versioning' | wc -l; done
0
0
0
```

No hay flags de object lock/versioning; se verificará por API en Tests de contrato.

Sonda (contenedor temporal, puertos solo en loopback; luego `docker stop sw-probe`):

```text
$ docker run -d --rm --name sw-probe -p 127.0.0.1:18333:8333 -p 127.0.0.1:19333:9333 \
    -e AWS_ACCESS_KEY_ID=probekey -e AWS_SECRET_ACCESS_KEY=<secret> \
    chrislusf/seaweedfs:4.48 server -dir=/data -s3
$ curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18333/healthz          -> 200
$ curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18333/                 -> 403 (sin firma)
$ curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:19333/cluster/status   -> 200
$ curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:19333/cluster/healthz  -> 200
$ docker exec sw-probe wget -qO- --server-response http://127.0.0.1:8333/healthz  -> HTTP/1.1 200 OK
$ docker logs sw-probe 2>&1 | grep "Added admin identity"
I1010 21:08:54.854023 auth_credentials.go:582 Added admin identity from AWS environment variables: name=admin-probekey, accessKey=probekey
```

Aviso en el log (extracto): `s3_sse_s3.go:861 SSE-S3 KeyManager: neither s3.sse.kek.passphrase nor WEED_S3_SSE_KEK_PASSPHRASE is set; the KEK will be stored on the filer in plaintext.`

Pendiente: la validación de firma con boto3 no se ejecutó en la inspección (boto3 no instalado en el entorno global).

## Configuración

Archivos: `docker-compose.spike.yml`, `.env.example` (el `.env` real está ignorado por git; se generó con credenciales aleatorias sin imprimirlas).

Arranque y verificación:

```text
$ docker compose -f docker-compose.spike.yml config --quiet && echo CONFIG_OK
CONFIG_OK
$ docker compose -f docker-compose.spike.yml up -d
$ docker compose -f docker-compose.spike.yml ps
pits-spike-seaweedfs  chrislusf/seaweedfs:4.48  "/entrypoint.sh serv…"  seaweedfs  Up 6 seconds (healthy)  127.0.0.1:8333->8333/tcp
$ docker inspect -f "{{.State.Health.Status}} {{.HostConfig.Memory}} {{.HostConfig.MemorySwap}}" pits-spike-seaweedfs
healthy 536870912 536870912
$ docker port pits-spike-seaweedfs
8333/tcp -> 127.0.0.1:8333
```

Reposo tras arrancar y disco libre del host:

```text
$ docker stats --no-stream --format "{{.Name}} {{.MemUsage}}" pits-spike-seaweedfs
pits-spike-seaweedfs 62.45MiB / 512MiB
$ df -h /c | tail -n 1
C:              476G  450G   26G  95% /c
```

Un solo contenedor corre master + volume + filer + S3 (`server -s3`).

Decisiones (el porqué, para quien viene de DA):

- `server -s3` en vez de `mini`: es el modo del plan aprobado y deja flags explícitos (`-volume.max`, límites). `mini` agrega Admin UI, Iceberg y WebDAV que no se necesitan.
- Credenciales por env (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, confirmado en paso 1): sin archivo de config que versionar; en el compose se leen de `.env` con `${VAR:?}`, que falla al instante si falta (fallo explícito en vez de un S3 sin identidad). Las variables del proyecto usan prefijo `S3_` para no chocar con credenciales AWS reales del entorno.
- Solo `127.0.0.1:8333`: master (9333), filer (8888) y sus puertos gRPC no deben salir del contenedor. Loopback evita exponer S3 a la red local.
- `mem_limit`/`memswap_limit` 512m + `GOMEMLIMIT=400MiB`: el límite del contenedor mata por OOM; `GOMEMLIMIT` hace que el GC de Go se esfuerce antes de llegar ahí. Igualar swap a memoria desactiva el swap. Es el equivalente a acotar un DataFrame antes de que reviente la RAM.
- `restart: "no"`: en un spike un crash debe verse, no reiniciarse en silencio.
- Volumen nombrado `pits_spike_seaweedfs_data`: datos persistentes y fáciles de borrar (`docker volume rm`) sin tocar el volumen de otros stacks.
- Healthcheck `curl -fsS .../healthz` (curl está en la imagen; `/healthz` verificado 200 en el paso 1): sin él, `depends_on: service_healthy` y los tests arrancarían antes de que S3 responda.

`-master.volumeSizeLimitMB=1024` con `-volume.max=0` (el entrypoint los antepone): `max=0` hace que weed calcule el máximo de volúmenes según el espacio libre del disco, y 1024 MB es el tope por volumen, no una reserva. Tras arrancar se crean 7 volúmenes casi vacíos (no se preasignan 1024 MB):

```text
$ docker exec pits-spike-seaweedfs sh -c 'ls -ls /data/*.dat; du -sh /data'
     4 -rw-r--r--    1 seaweed  seaweed          8 Oct 10 21:11 /data/1.dat
     (2.dat a 4.dat y 6.dat, 7.dat: igual, 8 bytes)
     4 -rw-r--r--    1 seaweed  seaweed        672 Oct 10 21:11 /data/5.dat
240.0K	/data
```

El host tiene ~26 GB libres (C: al 95%) y los tests de contrato usan objetos de hasta 128 MB, así que se mantiene 1024 y no se baja. Si las mediciones muestran crecimiento de disco inesperado, se revisará con `-master.volumeSizeLimitMB` menor.

## Tests de contrato

Archivos: `tests/contract/s3_helpers.py` (lógica pura: `load_settings`, `build_client`, `purge_bucket`, `BucketFactory`), `tests/contract/conftest.py` (solo fixtures `s3_settings`, `make_client`, `s3`, `make_bucket`, `bucket`), `tests/contract/test_s3_contract.py` (marker `contract`, requiere S3 vivo) y `tests/contract/test_s3_helpers.py` (offline, corre en la suite por defecto). La validación de settings es una función pura que lanza `SettingsError`; el fixture la convierte en `pytest.fail`. Los tests importan `s3_helpers` gracias a `pythonpath = ["tests/contract"]` en `[tool.pytest.ini_options]`, que no depende del import mode (verificado con el default y con `--import-mode=importlib`: 25 passed, 2 deselected en ambos). Los tests offline de `purge_bucket` cubren abort de multipart, borrado de versiones y delete markers, `VersionId` ausente, error de `delete_objects` (RuntimeError sin borrar el bucket) y lotes de 1000 (1001 versiones: 1000 + 1). Dependencia: `boto3` (dev; el lock fija 1.43.111). Los tests cargan todo desde env (`.env.example`): fallan con `pytest.fail` (no skip) si falta `S3_ENDPOINT_URL`, rechazan hosts distintos de `127.0.0.1`/`localhost`, y pasan las credenciales explícitas al cliente (nunca vía `AWS_*`). Los buckets se llaman `pits-contract-<uuid8>` y se limpian al final (abort de multipart, borrado paginado de versiones y delete markers, borrado del bucket); `make_bucket.keep(name)` excluye de la limpieza los buckets con objetos COMPLIANCE (paso 6).

Cómo correrlos:

```text
$ uv run pytest -q                                         # por defecto excluye contract
$ uv run --env-file .env pytest -m contract -q             # contra el S3 vivo
```

Por qué un marker en `addopts` y no en el workflow: en DA se corre "todo" a mano; en DE el CI debe ser determinista y sin servicios externos. `-m 'not contract'` en `addopts` hace que cualquier `pytest` (local, CI, pre-commit) excluya por defecto los tests que necesitan un S3 vivo, sin tocar `.github/workflows/ci.yml`. Para incluirlos se pasa `-m contract`: el `-m` de la CLI queda después del de `addopts` y gana (comprobado abajo).

Resultados del paso 3 (tras la revisión):

```text
$ uv run pytest -q
25 passed, 2 deselected in 1.77s
$ uv run --env-file .env pytest -m contract --collect-only -q
tests/contract/test_s3_contract.py::test_create_bucket
tests/contract/test_s3_contract.py::test_rejects_invalid_credentials
2/27 tests collected (25 deselected)
$ uv run --env-file .env pytest -m contract -q
2 passed, 25 deselected in 2.48s
$ env -u S3_ENDPOINT_URL uv run pytest -m contract -q
ERROR ... Failed: S3_END...   (mensaje completo: "S3_ENDPOINT_URL is required for contract tests (see .env.example)")
25 deselected, 2 errors in 0.37s
```

Credenciales inválidas: SeaweedFS 4.48 responde `Error.Code = InvalidAccessKeyId`, HTTP 403 (probado con boto3 1.43.111, `list_buckets` con clave falsa). El test exige que el código esté en `{InvalidAccessKeyId, SignatureDoesNotMatch, AccessDenied}`, sin aceptar un 403 cualquiera.

Hipótesis a verificar en el paso 4: boto3 recientes calculan checksums por defecto en `put_object`/multipart, lo que podría no ser compatible con SeaweedFS. Este paso solo ejercitó `create_bucket`/`head_bucket`/`list_buckets` sin errores; no hay evidencia aún sobre uploads.

## Mediciones

(pendiente)

## Qué funcionó / qué falló

(pendiente)

## Borrador D57

(pendiente)

## Borrador D58

(pendiente)

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

Hipótesis del paso 3 (checksums por defecto de boto3 en `put_object` podrían no ser compatibles con SeaweedFS): ver resultado del paso 4 abajo.

### Paso 4: objetos (put/get/list, vacíos, unicode, idempotencia)

Tests en `tests/contract/test_s3_contract.py`:

- `test_put_get_list`: 5 objetos bajo `data/` + 1 bajo `other/`; get con contenido exacto; `list_objects_v2` paginado con `PageSize=2` → páginas de 2+2+1; filtro por prefijo.
- `test_zero_byte_object`: `ContentLength == 0` y body `b""`.
- `test_unicode_and_space_keys`: keys NFC (`.../año fiscal/Bogotá D.C./señal.json`), otra con espacios dobles y `+`, y `raw/pct/100%25 done%2Fx %.json` (porcentajes que parecen URL-encoding); head/get/list devuelven la key idéntica en las tres (pasó sin xfail).
- `test_nfd_key_does_not_collide_with_nfc`: la misma key en NFC y en NFD son dos objetos distintos con su propio contenido (resultado del spike: SeaweedFS no normaliza Unicode).
- `test_reupload_same_key_is_idempotent`: un `put_object` de otro contenido (`{"a": 0}`) y luego dos del mismo contenido final en bucket sin versioning → mismo ETag igual a `"` + md5(body) + `"`, contenido final == body, 1 objeto en `list_objects_v2` y exactamente 1 versión (sin delete markers) en `list_object_versions` tras 3 PUT. Hallazgo: `put_object` no devuelve `VersionId` (`None`) y `list_object_versions` reporta la versión como `"null"` (verificado también con `get_object`: sin `VersionId`).

Resultado:

```text
$ uv run --env-file .env pytest -m contract -q
7 passed, 25 deselected in 4.23s
$ uv run pytest -q
25 passed, 7 deselected in 1.93s
```

Evidencia de limpieza: tras la corrida no quedan buckets (la identidad admin no tiene otros buckets en este stack de spike):

```text
$ uv run --env-file .env python -I -c "
import os,sys
sys.path.insert(0,'tests/contract')
from s3_helpers import *
s=load_settings(os.environ);c=build_client(s,s.access_key_id,s.secret_access_key)
print([b['Name'] for b in c.list_buckets()['Buckets']])"
[]
```

En la primera ejecución del test de reupload, la aserción `VersionId == "null"` falló con `AssertionError: assert {None} == {'null'}`; se corrigió la expectativa a lo observado (`None` en put, `"null"` en el listado) y no se tocó nada del servidor.

Hallazgo sobre checksums: con boto3 1.43.111 y la configuración por defecto (sin `request_checksum_calculation`/`response_checksum_validation`), `put_object`/`get_object` funcionaron contra SeaweedFS 4.48 sin error. La hipótesis no se confirmó para `put_object` con body pequeño; no se aplicó ningún `Config` especial. El multipart se prueba en el paso 5 (abajo). Además, `get_object` sin versioning devuelve `VersionId` `None` (ahora asertado).

### Paso 5: objeto grande en streaming (multipart)

`test_large_object_streaming` (marker `contract`, tamaño `S3_CONTRACT_LARGE_MB`, 128 MiB por defecto):

- Subida: `RandomStream` (en `s3_helpers.py`, `io.RawIOBase`) genera bloques de 1 MiB con `random.Random(42).randbytes` (no comprimible) y calcula sha256 al vuelo; `upload_fileobj` con `TransferConfig(multipart_threshold=8 MiB, multipart_chunksize=8 MiB, max_concurrency=2)` y `max_in_memory_upload_chunks=4` (atributo del config de s3transfer; no es argumento del constructor de boto3).
- Descarga: `get_object()["Body"].iter_chunks(1 MiB)` con sha256 al vuelo.
- Asserts: sha256 subido == descargado, `ContentLength == size`, ETag de `head_object` con sufijo `-N` (N = ceil(size/8 MiB); 16 con 128 MiB), y memoria: `peak < budget` con `budget = (max_in_memory_upload_chunks + max_concurrency) * 8 MiB + 16 MiB` (= 64 MiB, atado a la config) y `peak < size` (el cliente nunca tiene el objeto entero). No se usa `size/2`: con el mínimo de 100 MiB quedaría a ~3 % del umbral.
- `test_manual_multipart_etag_format`: `create_multipart_upload` -> 2 partes de 5 MiB + 1 de 1000 B -> `complete`; el ETag de `complete` y de `head_object` es `md5(concat(md5(parte_i))) + "-3"` (formato S3) y el contenido vuelve idéntico.
- Tests offline: `RandomStream` es determinista, no devuelve lecturas cortas, semillas distintas dan bytes distintos y `size=0` devuelve `b""` con el sha256 del vacío.

Resultado:

```text
$ uv run --env-file .env pytest -m contract -k large -q -s
large object: size=134217728 peak_tracemalloc=51798361 ETag="62ded3c249f6b76906d97f940270577e-16"
1 passed, 37 deselected in 7.60s
$ S3_CONTRACT_LARGE_MB=100 uv run --env-file .env pytest -m contract -k large -q -s
large object: size=104857600 peak_tracemalloc=51749572 ETag="99f26a313bdf5d6aa2a309387c467451-13"
1 passed, 37 deselected in 7.05s
$ uv run --env-file .env pytest -m contract -q
9 passed, 29 deselected in 11.40s
$ uv run pytest -q
29 passed, 9 deselected in 1.86s
```

Pico de memoria del cliente (tracemalloc): 51,8 MB con 128 MiB y 51,7 MB con 100 MiB (presupuesto: 64 MiB = 67,1 MB; el pico es casi independiente del tamaño del objeto, como se espera de un stream). Corridas anteriores dieron 50,9 y 51,8 MB.

Hallazgos del paso 5 (checksums de boto3 en multipart y dos trampas propias):

1. Checksums: el multipart completo (16 partes con `upload_fileobj`, y el multipart manual de 3 partes) funcionó con boto3 1.43.111 y la config por defecto, sin error. La hipótesis de incompatibilidad de checksums no se confirmó tampoco en multipart; no hizo falta `request_checksum_calculation="when_required"`.
2. Trampa 1 (mi código): la primera versión de `RandomStream.readinto` devolvía como máximo 1 MiB por llamada. s3transfer decide "PUT simple vs multipart" por lo que devuelve el primer `read(multipart_threshold)` en un stream no seekable; con lecturas cortas hizo un PUT simple (ETag sin `-N`, que indica PUT simple) aunque el contenido era correcto (la aserción de ETag `-16` falló con `'"9db2f92011a1265523c089170f2c35c3"'`). Con `readinto` que llena el buffer, sube multipart (sonda de 20 MiB: ETag `...-3`). Moraleja: un stream con lecturas cortas cambia silenciosamente la estrategia de subida.
3. Trampa 2: con la config por defecto (`max_in_memory_upload_chunks=10`, 8 MiB por parte) el pico de tracemalloc fue 95,8 MB y el primer criterio del test (`peak < size/2` = 67,1 MB) falló: `assert 95777375 < (134217728 / 2)`. Ojo: ni con el default el cliente cargaba el objeto entero (95,8 MB < 134 MB); no era un bug. Bajar a 4 chunks en memoria no corrige nada, fija una memoria conocida (~51 MB) y permite un presupuesto explícito. La memoria del cliente la acota ese parámetro, no el tamaño del objeto.
4. Observación (sin investigar la causa): un objeto de 20 MiB subido con lecturas cortas (ETag sin `-N`, presumiblemente PUT simple) devolvió `PartsCount=5` en `get_object(PartNumber=1)`.

## Mediciones

Parciales del paso 5 (el paso 7 las consolida). Contenedor `pits-spike-seaweedfs`, `mem_limit=512m`, `GOMEMLIMIT=400MiB`, host Windows/WSL (Docker 29.8.2). Comandos:

```text
docker stats --no-stream --format "{{.Name}} {{.MemUsage}} {{.MemPerc}}" pits-spike-seaweedfs
docker exec pits-spike-seaweedfs cat /sys/fs/cgroup/memory.peak
docker exec pits-spike-seaweedfs sh -c 'grep -E "^(anon|file|kernel) " /sys/fs/cgroup/memory.stat'
docker exec pits-spike-seaweedfs du -sh /data
docker inspect -f "{{.State.OOMKilled}}" pits-spike-seaweedfs
```

Secuencia limpia de memoria (la que dio los valores de la tabla de pico):

```text
$ docker restart pits-spike-seaweedfs      # espera healthy + 5 s
$ docker exec pits-spike-seaweedfs cat /sys/fs/cgroup/memory.peak
140484608
$ docker exec pits-spike-seaweedfs sh -c 'grep -E "^(anon|file|kernel) " /sys/fs/cgroup/memory.stat'
anon 132231168
file 1212416
kernel 1990656
$ uv run --env-file .env pytest -m contract -k large -q -s     # SOLO este test
1 passed, 37 deselected in 7.60s
$ docker exec pits-spike-seaweedfs cat /sys/fs/cgroup/memory.peak
461914112
$ docker exec pits-spike-seaweedfs cat /sys/fs/cgroup/memory.current
230187008
$ docker exec pits-spike-seaweedfs sh -c 'grep -E "^(anon|file|kernel) " /sys/fs/cgroup/memory.stat'
anon 225267712
file 1249280
kernel 2875392
$ docker inspect -f "OOM={{.State.OOMKilled}}" pits-spike-seaweedfs
OOM=false
```

| Medición | Valor |
|---|---|
| RAM en reposo (3 muestras de `docker stats` tras otro restart) | 129,2 / 128,4 / 128,3 MiB (25 %) |
| RAM durante el test (corrida anterior; 4 muestras, `docker stats` tarda ~3 s por muestra, resolución baja) | 128,3 -> 228,5 -> 236,7 -> 248,6 MiB |
| `memory.peak` tras restart + solo `-k large` (reposo: 140484608 B) | 461914112 B = 440,5 MiB |
| `memory.peak` en la corrida anterior (misma secuencia) | 440578048 B = 420,2 MiB |
| `memory.current` tras el test (anon / file / kernel) | 230187008 B (225267712 / 1249280 / 2875392) |
| OOMKilled | false |
| Disco `/data` antes | 596.0K |
| Disco tras subir 128 MiB (script manual, antes de borrar) | 128.7M |
| Disco tras borrar el bucket (inmediato y 30 s después) | 656.0K / 656.0K |

Notas:

- `memory.peak` es el máximo del cgroup completo (anon + page cache + kernel), no el heap de Go: no es comparable con `GOMEMLIMIT` (que acota el heap del runtime). El pico varió entre corridas (420,2 y 440,5 MiB); con 2 muestras no hay un intervalo fiable.
- Riesgo a medir en el paso 7: el pico del cgroup (420-441 MiB) queda a ~70-90 MiB del límite de 512 MiB con un solo objeto de 128 MiB y concurrencia 2; con más concurrencia u objetos mayores el margen podría agotarse. Es una hipótesis de riesgo, no un hecho medido.
- `memory.peak` es acumulado desde el arranque del contenedor y es de solo lectura (`echo 0 > /sys/fs/cgroup/memory.peak` -> `Read-only file system`), por eso se mide tras un `docker restart`. Una medición previa sin reiniciar dio 475086848 B porque incluía corridas anteriores.
- Disco: se midió con un script manual (no con el test) porque el fixture borra el bucket al terminar y el test no debe depender de `docker`. El script, tal cual se ejecutó (`uv run --env-file .env python -I disk.py`, credenciales por entorno vía `load_settings`/`build_client`):

```python
import os, sys, subprocess, time

sys.path.insert(0, "tests/contract")
from s3_helpers import *
from boto3.s3.transfer import TransferConfig


def du(label):
    out = subprocess.run(
        ["docker", "exec", "pits-spike-seaweedfs", "du", "-sh", "/data"],
        capture_output=True,
        text=True,
    ).stdout.split()[0]
    print(f"{label}: {out}", flush=True)


s = load_settings(os.environ)
c = build_client(s, s.access_key_id, s.secret_access_key)
b = "pits-contract-disk1"
c.create_bucket(Bucket=b)
du("before")
cfg = TransferConfig(multipart_threshold=8 * MIB, multipart_chunksize=8 * MIB, max_concurrency=2)
cfg.max_in_memory_upload_chunks = 4
src = RandomStream(128 * MIB)
c.upload_fileobj(src, b, "blob", Config=cfg)
du("after_upload")
purge_bucket(c, b)
du("after_delete_immediate")
time.sleep(30)
du("after_delete_30s")
```

```text
before: 596.0K
after_upload: 128.7M
after_delete_immediate: 656.0K
after_delete_30s: 656.0K
```

- Al borrar el bucket el espacio se liberó de inmediato (128.7M -> 656.0K). Mi hipótesis previa ("SeaweedFS no libera hasta vacuum") no se cumplió para el borrado del bucket completo; no se probó borrar objetos dentro de un bucket que sigue existiendo (ahí sí podría hacer falta vacuum).
- Se retiró la fila de `docker system df -v` (376,4 kB frente a 656K de `du`; otra lectura dio 610,6 kB frente a 904K): las cifras no cuadran y no hay evidencia para explicar la diferencia (podría ser cómo cuenta Docker el volumen frente a `du` dentro del contenedor, pero no se verificó).

## Qué funcionó / qué falló

(pendiente)

## Borrador D57

(pendiente)

## Borrador D58

(pendiente)

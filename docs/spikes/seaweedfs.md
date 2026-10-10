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
- Asserts: sha256 subido == descargado, `ContentLength == size`, ETag de `head_object` con sufijo `-N` (N = ceil(size/8 MiB); 16 con 128 MiB), y memoria: `peak < budget` con `budget = (max_in_memory_upload_chunks + max_concurrency) * 8 MiB + 16 MiB` (= 64 MiB, atado a la config) y `peak < size` (aserción documental: la implica el presupuesto, que es menor que `size` desde 100 MiB). No se usa `size/2`: con el mínimo de 100 MiB quedaría a ~1,3–3 % del umbral (picos de 50,9 y 51,7 MB en dos corridas contra 52,4 MB).
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

### Paso 6: versioning y Object Lock

Tests en `tests/contract/test_s3_contract.py` (marker `contract`). Antes de escribirlos se hizo una sonda manual (`probe_lock.py` en el scratchpad) con los mismos pasos para ver el comportamiento real (la sonda no se conserva; los tests reproducen sus pasos); no se ajustó ninguna expectativa: todo coincidió con la expectativa de los tests; no hizo falta `xfail`.

Resultados por caso (`uv run --env-file .env pytest -m contract -q -rA`, 14 passed, 30 deselected in 20.25s; códigos literales de `ClientError`):

| Caso | Resultado | Detalle observado |
|---|---|---|
| `test_versioning` | pasa | `put_bucket_versioning Enabled`; 2 puts -> 2 versiones distintas; `get(VersionId=v1)` = contenido viejo; `delete_object` sin VersionId -> `DeleteMarker: True` (1 marker en `list_object_versions`); v1 sigue legible; `get_object` sin versión -> `NoSuchKey` / 404 |
| `test_object_lock_enabled_bucket` (a) | pasa | `get_object_lock_configuration` -> `ObjectLockEnabled: Enabled`; `get_bucket_versioning` -> `Enabled` (se activa solo al crear el bucket con `ObjectLockEnabledForBucket=True`) |
| `test_object_lock_compliance` (b): `delete_object(VersionId=v1)` | pasa (falla como debe) | `AccessDenied` / 403 ("Access Denied.") |
| (b) delete con `BypassGovernanceRetention=True` | pasa (falla como debe) | `AccessDenied` / 403 |
| (b) `put_object_retention` acortando la fecha | pasa (falla como debe) | `AccessDenied` / 403 |
| (b) `get_object_retention(VersionId=v1)` | pasa | `Mode: COMPLIANCE`, `RetainUntilDate` = la enviada, truncada a segundos (la sonda: enviada 21:38:56.7 -> devuelta 21:40:56) |
| (b) control positivo: `put_object_retention` alargando la fecha de v1 (+1 min) | pasa | HTTP 200; `get_object_retention` devuelve la fecha nueva (a los segundos); acortarla da `AccessDenied` / 403, así que la retención COMPLIANCE solo se puede alargar |
| (b) sobrescribir la misma key | pasa | `put_object` tiene éxito y crea `v2`; v1 conserva los bytes (sha256 igual) y su retención |
| (b) control: v2 sin retención | pasa | `get_object_retention(v2)` -> `ObjectLockConfigurationNotFoundError` / 404 ("Object Lock configuration does not exist for this bucket"; mensaje poco preciso para una versión sin retención, no contrastado con AWS); `delete_object(VersionId=v2)` con la misma identidad tiene éxito, así que el 403 de v1 se debe a la retención y no a falta de permisos |
| (b) `delete_object` sin VersionId | pasa | `DeleteMarker: True`; v1 legible por VersionId |
| (b) desfase de reloj | pasa | cabecera `Date` del servidor frente a reloj del cliente: 0,1 s (el test exige < 30 s) |
| `test_object_lock_governance_bypass` (c): delete sin bypass | pasa (falla como debe) | `AccessDenied` / 403 |
| (c) delete con `BypassGovernanceRetention=True` | pasa | éxito (identidad admin); devuelve el `VersionId` borrado. Ojo: esto no prueba que una identidad sin el permiso de bypass (`s3:BypassGovernanceRetention`) sea rechazada; ver la limitación de identidad única admin bajo la tabla |
| `test_object_lock_legal_hold` (d) | pasa | hold ON -> `get_object_legal_hold` = `ON`, delete de la versión `AccessDenied` / 403; hold OFF -> delete con éxito |

Sin divergencias respecto a la expectativa de los tests en los casos probados; no se registró ningún `xfail`. No se verificó contra la documentación de AWS ni de SeaweedFS (solo contra la expectativa de los tests), y no se probó el mismo flujo con una identidad no admin (la única identidad es la admin del env), que es donde Object Lock suele aportar valor real.

Limpieza: los buckets con retención activa no se pueden vaciar hasta que expira (COMPLIANCE y, sin bypass, GOVERNANCE). Los tests los marcan con `make_bucket.keep()`. La fixture `s3` (sesión) llama a `purge_contract_buckets` al empezar cada corrida `contract`, como mejor esfuerzo: purga los restos de corridas anteriores cuya retención ya expiró e emite un `warnings.warn` (sin fallar; aparece en el resumen de warnings de pytest) para los que siguen retenidos, p. ej. `leftover contract bucket not purged (retention still active?): pits-contract-c2117663: RuntimeError("delete_objects failed ... 'Code': 'AccessDenied' ...")`. Riesgo: dos sesiones `-m contract` simultáneas contra el mismo endpoint pueden purgarse mutuamente los buckets de prueba (el prefijo `pits-contract-` es común); no las lances en paralelo. Es decir, los buckets COMPLIANCE de la corrida actual se purgan en la siguiente corrida o a mano con `purge.py` pasados ~3 min (el test alarga la retención de v1 a +3 min en total). Antes de que expiren, el purgado falla con la causa literal:

```text
$ uv run --env-file .env python -I purge.py     # purge_contract_buckets de s3_helpers, a los ~20 s
before: ['pits-contract-01f609f1', 'pits-contract-187ef214', 'pits-contract-b444d762']
ERR pits-contract-187ef214: RuntimeError("delete_objects failed in pits-contract-187ef214: [{'Key': 'k', 'VersionId': '6722b723fe76707d161dffc531ee736d', 'Code': 'AccessDenied', 'Message': 'Access Denied.'}]")
ERR pits-contract-b444d762: RuntimeError("delete_objects failed in pits-contract-b444d762: [{'Key': 'raw/compliance.bin', 'VersionId': '6722b71b1306a990257d8c388ba01cb1', 'Code': 'AccessDenied', 'Message': 'Access Denied.'}]")
after: ['pits-contract-187ef214', 'pits-contract-b444d762']
```

Pasada la retención (2 min en esta salida, anterior al control de alargado; ahora 3 min), el mismo comando los vacía y los borra:

```text
$ uv run --env-file .env python -I purge.py
before: ['pits-contract-187ef214', 'pits-contract-b444d762']
after: []
```

`purge.py` (se ejecuta con las credenciales del entorno; sin secretos en el script):

```python
import os, sys

sys.path.insert(0, "tests/contract")
from s3_helpers import *

s = load_settings(os.environ)
c = build_client(s, s.access_key_id, s.secret_access_key)
print("before:", [b["Name"] for b in c.list_buckets()["Buckets"]])
for e in purge_contract_buckets(c):
    print("ERR", e[:230])
print("after:", [b["Name"] for b in c.list_buckets()["Buckets"]])
```

(El bucket GOVERNANCE `pits-contract-01f609f1` se purgó en la primera pasada porque su única versión ya se había borrado con bypass.) Estado final tras la corrida completa de `-m contract` (dos buckets con retención, `pits-contract-1390e859` y `pits-contract-b47ddae8`; purgados ~2 min después con el mismo script):

```text
before: ['pits-contract-1390e859', 'pits-contract-b47ddae8']
after: []
```

## Mediciones

### Medición final consolidada (paso 7)

Contenedor `pits-spike-seaweedfs`, `mem_limit=512m`, `GOMEMLIMIT=400MiB`, Docker 29.8.2 sobre WSL2. Una sola secuencia limpia (script y salida cruda en "Script y salida cruda de la medición final", abajo):

1. `docker restart pits-spike-seaweedfs` -> healthy a las 21:57:57.
2. Reposo de 2 min (hasta 21:59:57), luego 3 muestras de `docker stats`, `memory.peak`, `memory.current`, `memory.stat` y `du -sh /data`.
3. Corrida completa `uv run --env-file .env pytest -m contract -q -s` (14 tests, 22:00:06-22:00:21) con un muestreo de `docker stats` en background (~1 muestra cada 3 s: `docker stats` tarda ese tiempo por llamada).
4. Justo después: `memory.peak`, `memory.current`, `memory.stat`, OOMKilled, `du -sh /data`.
5. Script de disco (`disk.py`, ya en el doc: sube 128 MiB, mide, borra el bucket, mide inmediato y a los 30 s). Se ejecutó después de leer `memory.peak`, así que no contamina el pico.

| Medición | Valor | Corrida |
|---|---|---|
| RAM en reposo (3 muestras de `docker stats`, tras 2 min de reposo) | 130,6 / 130,3 / 130,5 MiB (25,5 %) | restart de la secuencia final |
| Reposo: `memory.peak` / `memory.current` | 147222528 B (140,4 MiB) / 142741504 B (136,1 MiB) | ídem |
| Reposo: `memory.stat` anon / file / kernel | 134287360 / 5668864 / 2035712 B | ídem |
| RAM durante la corrida completa (5 muestras) | 130,4 -> 131,7 -> 236,9 -> 249,9 -> 253,5 MiB | corrida completa `-m contract` |
| Pico del cgroup (`memory.peak` tras la corrida completa) | 479043584 B = 456,8 MiB (89 % de 512 MiB) | ídem |
| `memory.current` tras la corrida | 265564160 B (anon 255598592 / file 5873664 / kernel 3117056) | ídem |
| OOMKilled / reinicios | false / 0 | ídem |
| Pico en corridas anteriores (solo `-k large`, tras restart) | 420,2 MiB (paso 5, 1.ª) y 440,5 MiB (paso 5, 2.ª) | pasos 5 |
| Pico del cliente (tracemalloc, test de 128 MiB) | 51,8 MB (presupuesto 64 MiB) | corrida completa |
| Disco `/data` en reposo (antes de la corrida) | 1.6M | restart de la secuencia final |
| Disco `/data` tras la corrida completa (con 2 buckets con retención aún vivos) | 1.8M | corrida completa |
| Disco: antes / tras subir 128 MiB (`disk.py`, antes de borrar) | 1.8M / 129.9M | `disk.py` posterior |
| Disco: tras borrar el bucket (inmediato / 30 s) | 1.8M / 2.0M | `disk.py` posterior |

Lectura: el pico de memoria del cgroup fue 420,2 / 440,5 / 456,8 MiB: variación 420–457 MiB en 3 corridas no comparables (dos con solo `-k large`, una con la suite completa); no hay datos para afirmar una tendencia. La última incluye todos los tests (multipart de 128 MiB, 5 MiB x 2 del multipart manual, Object Lock, etc.), no solo el test grande, y con 3 muestras no hay un intervalo fiable. Es la principal razón para proponer más margen en D57. El disco crece ~128 MiB al subir el objeto y vuelve al valor base al borrar el bucket (la diferencia de 0,2M a los 30 s no se investigó).

### Script y salida cruda de la medición final

`final.sh` tal cual se ejecutó (no contiene secretos; `uv run --env-file .env` carga las credenciales sin imprimirlas):

```bash
export MSYS_NO_PATHCONV=1
cd /c/dev/pits-app-spike
S='<scratchpad>'
C=pits-spike-seaweedfs
st() { docker exec $C sh -c 'grep -E "^(anon|file|kernel) " /sys/fs/cgroup/memory.stat'; }
echo "## restart"; docker restart $C >/dev/null
until [ "$(docker inspect -f '{{.State.Health.Status}}' $C)" = healthy ]; do sleep 2; done; echo "healthy at $(date -u +%T)"
sleep 120
echo "## idle samples ($(date -u +%T))"; for i in 1 2 3; do docker stats --no-stream --format "{{.Name}} {{.MemUsage}} {{.MemPerc}}" $C; done
echo "idle memory.peak: $(docker exec $C cat /sys/fs/cgroup/memory.peak)"; echo "idle memory.current: $(docker exec $C cat /sys/fs/cgroup/memory.current)"; st
echo "du idle: $(docker exec $C du -sh /data)"
(while true; do echo "$(date -u +%T) $(docker stats --no-stream --format '{{.MemUsage}}' $C)"; sleep 1; done > "$S/mem_final.log") &
SP=$!
echo "## full contract run start $(date -u +%T)"
uv run --env-file .env pytest -m contract -q -s 2>&1 | grep -E "large object|passed|failed|leftover"
echo "## full contract run end $(date -u +%T)"
kill $SP; sleep 2
echo "peak: $(docker exec $C cat /sys/fs/cgroup/memory.peak)"; echo "current: $(docker exec $C cat /sys/fs/cgroup/memory.current)"; st
docker inspect -f "OOM={{.State.OOMKilled}} restarts={{.RestartCount}}" $C
echo "du after run: $(docker exec $C du -sh /data)"
echo "## samples during run"; cat "$S/mem_final.log"
echo "## disk script"; uv run --env-file .env python -I "$S/disk.py" 2>&1 | tail -5
echo "## done $(date -u +%T)"
```

Salida cruda (`final.log`):

```text
## restart
healthy at 21:57:57
## idle samples (21:59:57)
pits-spike-seaweedfs 130.6MiB / 512MiB 25.51%
pits-spike-seaweedfs 130.3MiB / 512MiB 25.44%
pits-spike-seaweedfs 130.5MiB / 512MiB 25.49%
idle memory.peak: 147222528
idle memory.current: 142741504
anon 134287360
file 5668864
kernel 2035712
du idle: 1.6M	/data
## full contract run start 22:00:06
.......large object: size=134217728 peak_tracemalloc=51751400 ETag="62ded3c249f6b76906d97f940270577e-16"
14 passed, 30 deselected in 13.01s
## full contract run end 22:00:21
peak: 479043584
current: 265564160
anon 255598592
file 5873664
kernel 3117056
OOM=false restarts=0
du after run: 1.8M	/data
## samples during run
22:00:06 130.4MiB / 512MiB
22:00:09 131.7MiB / 512MiB
22:00:12 236.9MiB / 512MiB
22:00:15 249.9MiB / 512MiB
22:00:17 253.5MiB / 512MiB
## disk script
before: 1.8M
after_upload: 129.9M
after_delete_immediate: 1.8M
after_delete_30s: 2.0M
## done 22:01:07
```

### Mediciones parciales del paso 5 (histórico)

Contenedor `pits-spike-seaweedfs`, `mem_limit=512m`, `GOMEMLIMIT=400MiB`, host Windows/WSL (Docker 29.8.2). Comandos:

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
| Disco `/data` antes / tras subir 128 MiB (script manual, antes de borrar) | 1.3M / 129.3M (1.ª ejecución: 596.0K / 128.7M) |
| Disco tras borrar el bucket (inmediato y 30 s después) | 1.3M / 1.3M (1.ª ejecución: 656.0K / 656.0K) |

Notas:

- `memory.peak` es el máximo del cgroup completo (anon + page cache + kernel), no el heap de Go: no es comparable con `GOMEMLIMIT` (que acota el heap del runtime). El pico varió entre corridas (420,2 y 440,5 MiB); con 2 muestras no hay un intervalo fiable.
- Riesgo a medir en el paso 7: el pico del cgroup (420-441 MiB) queda a ~70-90 MiB del límite de 512 MiB con un solo objeto de 128 MiB y concurrencia 2; con más concurrencia u objetos mayores el margen podría agotarse. Es una hipótesis de riesgo, no un hecho medido.
- `memory.peak` es acumulado desde el arranque del contenedor y es de solo lectura (`echo 0 > /sys/fs/cgroup/memory.peak` -> `Read-only file system`), por eso se mide tras un `docker restart`. Una medición previa sin reiniciar dio 475086848 B porque incluía corridas anteriores.
- Disco: se midió con un script manual (no con el test) porque el fixture borra el bucket al terminar y el test no debe depender de `docker`. El script, tal cual se ejecutó (`uv run --env-file .env python -I disk.py`, credenciales por entorno vía `load_settings`/`build_client`):

```python
import os, sys, subprocess, time, uuid

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
b = f"pits-contract-disk-{uuid.uuid4().hex[:8]}"
c.create_bucket(Bucket=b)
try:
    du("before")
    cfg = TransferConfig(
        multipart_threshold=8 * MIB, multipart_chunksize=8 * MIB, max_concurrency=2
    )
    cfg.max_in_memory_upload_chunks = 4
    src = RandomStream(128 * MIB)
    c.upload_fileobj(src, b, "blob", Config=cfg)
    du("after_upload")
finally:
    purge_bucket(c, b)
du("after_delete_immediate")
time.sleep(30)
du("after_delete_30s")
```

```text
before: 1.3M
after_upload: 129.3M
after_delete_immediate: 1.3M
after_delete_30s: 1.3M
```

(Segunda ejecución del script, ya con nombre de bucket único y `try/finally`; el "antes" de 1.3M incluye los objetos bloqueados por Object Lock del paso 6 aún retenidos. La primera ejecución, con bucket fijo, dio 596.0K / 128.7M / 656.0K / 656.0K: mismo comportamiento, subida de ~128 MiB y liberación inmediata al borrar el bucket.)

- Al borrar el bucket el espacio se liberó de inmediato (129.3M -> 1.3M; 1.ª ejecución 128.7M -> 656.0K). Mi hipótesis previa ("SeaweedFS no libera hasta vacuum") no se cumplió para el borrado del bucket completo; no se probó borrar objetos dentro de un bucket que sigue existiendo (ahí sí podría hacer falta vacuum).
- Se retiró la fila de `docker system df -v` (376,4 kB frente a 656K de `du`; otra lectura dio 610,6 kB frente a 904K): las cifras no cuadran y no hay evidencia para explicar la diferencia (podría ser cómo cuenta Docker el volumen frente a `du` dentro del contenedor, pero no se verificó).

## Qué funcionó / qué falló / con matices

Resumen: no hubo ninguna falla dura. `14 passed` en `-m contract` (contra SeaweedFS 4.48 real) y `30 passed` offline; no se registró ningún `xfail`. Los matices, con su evidencia:

**Resultado de las hipótesis**

- H1 (API S3 compatible con boto3/s3fs/dbt): confirmada solo con boto3 1.43.111 en modo path-style. s3fs y dbt NO se probaron.
- H2 (identidad S3 solo con variables de entorno): confirmada (paso 1; log `Added admin identity from AWS environment variables` y tests con esas credenciales).
- H3 (endpoint de salud usable en un healthcheck): confirmada (`/healthz` 200 con `curl -fsS`; el contenedor queda `healthy`).

**Funcionó**

- Compatibilidad S3 con boto3 1.43.111 (path-style, credenciales por entorno): buckets, put/get/list, paginación, objetos vacíos, keys Unicode/espacios/`%`, NFC y NFD como objetos distintos, re-subida idempotente (pasos 3-4).
- Multipart y streaming de 128 MiB (y 100 MiB) con hash verificado y memoria del cliente acotada (~51 MB); ETag multipart en formato S3 (paso 5).
- Versioning, delete markers, Object Lock COMPLIANCE/GOVERNANCE y legal hold con los códigos esperados (`AccessDenied` / 403) (paso 6).
- Hipótesis de checksums de boto3 >=1.36: no se confirmó, ni en `put_object` ni en multipart; no hizo falta configuración especial (pasos 4-5).
- Persistencia: un objeto testigo sobrevive a `docker compose down` + `up -d` (sección "Persistencia", hash idéntico).
- Credenciales por variables de entorno (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`) sin archivo de config (paso 1); healthcheck `/healthz` estable.

**Con matices (a tener en cuenta al decidir)**

1. Memoria (hallazgo principal para dimensionar): con un solo objeto de 128 MiB y concurrencia 2, `memory.peak` del cgroup fue 420,2 / 440,5 / 456,8 MiB en tres corridas (la última, la corrida completa de `-m contract`), es decir 82-89 % del límite de 512 MiB. `GOMEMLIMIT` acota el heap de Go y `memory.peak` mide el cgroup completo: no son comparables. No hubo OOM, pero el margen es corto y no hay datos para afirmar una tendencia (ver "Lectura" de la medición final); con más concurrencia u objetos mayores no está medido.
2. `put_object` sin versioning no devuelve `VersionId` (`None`) y `list_object_versions` reporta la versión como `"null"` (paso 4).
3. `get_object_retention` de una versión sin retención devuelve `ObjectLockConfigurationNotFoundError` / 404 con el mensaje "Object Lock configuration does not exist for this bucket", impreciso para ese caso (no contrastado con AWS) (paso 6).
4. Disco: al borrar un bucket completo el espacio se liberó de inmediato (129,9 MiB -> 1,8 MiB); no se probó borrar objetos dentro de un bucket que sigue vivo (ahí podría hacer falta vacuum) ni el crecimiento a largo plazo.
5. Identidad única admin: no se probó el comportamiento con identidades sin `s3:BypassGovernanceRetention` ni con permisos acotados; Object Lock solo está probado frente a la identidad que además puede usar el bypass.
6. Observación sin investigar: un objeto de 20 MiB subido con lecturas cortas (ETag sin `-N`) devolvió `PartsCount=5` en `get_object(PartNumber=1)`.
7. Entorno: Docker sobre WSL2 en Windows, con el disco C: al 95 % (26 GB libres). Los números de memoria y disco pueden diferir en el VPS (Linux nativo).
8. Aviso del log: la KEK de SSE-S3 se guarda en texto plano en el filer si no se define `s3.sse.kek.passphrase`; el cifrado en reposo no está habilitado en este spike.
9. Trampas propias (dejaron lecciones, no son fallas de SeaweedFS): un stream con lecturas cortas cambia silenciosamente PUT simple/multipart; la memoria del cliente la acota `max_in_memory_upload_chunks`, no el tamaño del objeto.
10. s3fs y dbt no probados: la compatibilidad S3 está verificada solo con boto3 (H1); queda pendiente antes de fijar D57.
11. Operativo: cada corrida `-m contract` deja 2 buckets con retención (2-3 min) que se purgan en la siguiente corrida o con `purge.py`; no correr dos sesiones a la vez.

## Persistencia y apagado

Script `persist.py` (credenciales del entorno vía `load_settings`/`build_client`; `write` sube un objeto de 5 MiB aleatorio a `pits-contract-persist-<uuid8>` y guarda bucket y sha256 en un archivo temporal; `verify` lo relee; `purge` limpia):

```python
"""Persistence check: `write` stores a witness object, `verify` reads it back, `purge` cleans up."""

import hashlib
import os
import sys
import uuid

sys.path.insert(0, "tests/contract")
from s3_helpers import build_client, load_settings, purge_bucket

STATE = os.path.join(os.environ.get("TEMP", "."), "pits_persist_state.txt")
KEY = "raw/persist/witness.bin"
s = load_settings(os.environ)
c = build_client(s, s.access_key_id, s.secret_access_key)
mode = sys.argv[1]
if mode == "write":
    bucket = f"pits-contract-persist-{uuid.uuid4().hex[:8]}"
    body = os.urandom(5 * 1024 * 1024)
    c.create_bucket(Bucket=bucket)
    c.put_object(Bucket=bucket, Key=KEY, Body=body)
    digest = hashlib.sha256(body).hexdigest()
    open(STATE, "w").write(f"{bucket} {digest}")
    print(f"written bucket={bucket} sha256={digest}")
elif mode == "verify":
    bucket, digest = open(STATE).read().split()
    got = hashlib.sha256(c.get_object(Bucket=bucket, Key=KEY)["Body"].read()).hexdigest()
    print(f"read bucket={bucket} sha256={got} equal={got == digest}")
elif mode == "purge":
    bucket, _ = open(STATE).read().split()
    purge_bucket(c, bucket)
    print("purged", bucket, "->", [b["Name"] for b in c.list_buckets()["Buckets"]])
```

Secuencia y salida:

```text
$ uv run --env-file .env python -I persist.py write
written bucket=pits-contract-persist-29431c1f sha256=0add5a81785b79fa7646af36dca31547507671b6618bf1aa151a699a4c39d015
$ docker compose -f docker-compose.spike.yml down          # SIN -v
 Container pits-spike-seaweedfs Removed
 Network pits-spike_default Removed
$ docker ps -a --filter name=pits-spike --format "{{.Names}}"
(vacío)
$ docker volume ls --filter name=pits_spike
DRIVER    VOLUME NAME
local     pits_spike_seaweedfs_data
$ docker compose -f docker-compose.spike.yml up -d
 Container pits-spike-seaweedfs Started          # luego espera healthy
$ uv run --env-file .env python -I persist.py verify
read bucket=pits-contract-persist-29431c1f sha256=0add5a81785b79fa7646af36dca31547507671b6618bf1aa151a699a4c39d015 equal=True
$ uv run --env-file .env python -I persist.py purge
purged pits-contract-persist-29431c1f -> ['pits-contract-5c28fbaf', 'pits-contract-ba11a24e']
```

(Los dos buckets restantes son los de la corrida completa, con retención activa en ese momento; se purgaron después con `purge.py`.)

Apagado final del spike (los dos buckets con retención de la corrida completa se purgaron antes; `list_buckets()` -> `[]`):

```text
$ docker compose -f docker-compose.spike.yml down          # SIN -v
 Container pits-spike-seaweedfs Removed
 Network pits-spike_default Removed
$ docker ps -a --filter name=pits-spike --format "{{.Names}}"
(vacío)
$ docker volume ls --filter name=pits_spike
DRIVER    VOLUME NAME
local     pits_spike_seaweedfs_data
```

Para volver a levantarlo: `docker compose -f docker-compose.spike.yml up -d` (usa el `.env` local).

Para borrar el volumen (destructivo; decisión de Henry, no se ejecutó): `docker compose -f docker-compose.spike.yml down -v`, o solo el volumen con `docker volume rm pits_spike_seaweedfs_data`.

## Borrador D57

Estado: Propuesta (pendiente de aprobación de Henry; no está en `docs/05_decisions_log.md`). Formato idéntico a las filas de `05`:

| D57 | Propuesta (2026-10-10) | Storage S3 local y de despliegue: SeaweedFS `chrislusf/seaweedfs:4.48` (digest `sha256:4e61d15fd35994cb1e43e1e553dff106794841fd9a99ade2fc8c8bfce4d7872d`), un contenedor `server -s3` (master + volume + filer + S3), solo `127.0.0.1:8333` publicado, volumen nombrado, credenciales admin desde `.env` (`S3_ACCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY` mapeadas a `AWS_*`). `tests/contract` es el contrato del storage (marker `contract`, ver D58). Límite de memoria: ver opciones M1/M2 abajo (recomendada M1: `mem_limit` 768m + `GOMEMLIMIT` 600MiB; no validada a 768m; validación en VPS pendiente). Pendiente: compatibilidad con s3fs y dbt no probada (solo boto3). Inmutabilidad del raw (D29): opciones A/B abajo, pendiente de Henry (recomendada A). | MinIO comunitario ya no se distribuye (`06_status.md` §5: repo `minio/minio` archivado 2026-04-25, imágenes `minio/minio` y `minio/mc` en 404 en Docker Hub, CVE altos sin parche libre como CVE-2026-41145). Evidencia del spike (`docs/spikes/seaweedfs.md`): 14/14 tests de contrato y 30/30 offline pasan, sin `xfail`; multipart y streaming de 128 MiB con hash verificado; versioning y Object Lock (COMPLIANCE, GOVERNANCE, legal hold) con los códigos esperados; persistencia tras `down`/`up -d` con hash idéntico; reposo ~130 MiB; `memory.peak` 420-457 MiB con un objeto de 128 MiB y concurrencia 2 (82-89 % de 512 MiB); sin OOM; 129,9 MiB en disco para 128 MiB, liberados al borrar el bucket. | MinIO (imágenes sin distribución libre y repo archivado); Garage y otras alternativas S3 no evaluadas en este spike; almacenamiento en filesystem local sin S3 (rompe la ruta `raw/...` de `04_infra.md` §8.1 y el paso a un S3 real) |

**Opciones de memoria (a decidir):**

- M1 (recomendada): `mem_limit` y `memswap_limit` 768m con `GOMEMLIMIT` 600MiB. Con el pico medido de ~457 MiB deja ~310 MiB de margen (~40 %) y 768 MiB ≈ 0,75 GiB, en el límite superior del rango 0,3–0,8 GB de `04_infra.md` §9 (escrito para MinIO). Se justifica por el margen sobre el máximo observado (457 MiB; ver "Lectura" de la medición final). Hay que validarlo con una corrida de `-m contract` a 768m (no se hizo en este spike).
- M2: mantener 512m y limitar la concurrencia de los clientes (`max_concurrency=1`, objetos <= 128 MiB, partes de 8 MiB). Ahorra RAM, pero el margen actual es de 55 MiB (11 %) con concurrencia 2, el efecto de limitarla no está medido y un cliente mal configurado puede provocar OOM del storage (afecta a todo el stack: D9 protege al resto del VPS, pero no al propio storage).

**Opciones de inmutabilidad del raw (D29), pendiente de Henry:**

- A (recomendada): convención write-once por `batch_id` (la ruta `raw/<source_system>/extraction_date=.../batch_id=<uuid>/payload.*` ya es única por lote, `04_infra.md` §8.1) + versioning activado en el bucket raw para proteger contra sobrescrituras accidentales. Sin dependencia de permisos IAM finos. Diferencia con B: el versioning protege de sobrescrituras accidentales, no de borrados deliberados de versiones por la misma identidad; B sí los impide solo con COMPLIANCE, o con GOVERNANCE si la identidad de ingesta no tiene `s3:BypassGovernanceRetention` (requiere identidades separadas, no probadas).
- B: Object Lock GOVERNANCE en el bucket raw. Evidencia: funciona (delete sin bypass `AccessDenied`, con bypass éxito para la identidad admin), pero con la identidad única admin el bypass está disponible, así que no protege contra el propio proceso de ingesta; requeriría identidades separadas (no probadas en este spike). COMPLIANCE impide vaciar el bucket hasta que expira la retención (impráctico para raw con reprocesos).

## Borrador D58

Estado: Propuesta (pendiente de aprobación de Henry; no está en `docs/05_decisions_log.md`).

| D58 | Propuesta (2026-10-10) | Los tests de contrato del storage S3 (`tests/contract`, marker `contract`) quedan excluidos por defecto con `-m 'not contract'` en `addopts` (`pyproject.toml`) y se corren a mano con `uv run --env-file .env pytest -m contract` contra un endpoint local (`127.0.0.1`/`localhost`, validado por `load_settings`). El CI (`.github/workflows/ci.yml`) no los corre hasta que exista un job con service container de SeaweedFS (se retomará cuando haya Docker Compose del stack core). Los tests offline de `s3_helpers` sí corren siempre. Los buckets de prueba (`pits-contract-<uuid8>`) se limpian solos; los que tienen retención se purgan en la corrida siguiente o con `purge_contract_buckets`. | Un `pytest` por defecto debe ser determinista y no depender de servicios externos (CI y pre-commit verdes sin Docker); el `-m` de la CLI gana sobre el de `addopts` (verificado en el paso 3). | Marker con `skip` automático si falta el endpoint (oculta fallos de configuración: aquí un endpoint ausente falla con `pytest.fail`); correr los contract tests siempre en CI con service container ahora (aún no hay compose del stack ni job); un directorio fuera de `tests/` con su propio runner (duplica configuración) |

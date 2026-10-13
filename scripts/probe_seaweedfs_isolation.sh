#!/usr/bin/env bash
# Sonda de aislamiento de listeners de SeaweedFS (hito B, D117-D120). NO toca pits-seaweedfs ni el
# proyecto compose "pits": usa el proyecto "pits-swprobe", el volumen pits_swprobe_data y el puerto
# host 127.0.0.1:28333. Credenciales y clave JWT aleatorias en un directorio temporal; no lee .env
# y no imprime secretos (no usar `bash -x`).
# Fase 1 (linea base, command actual de compose): levanta con s3.json, escribe un objeto testigo
#   (sha256) y mide desde un contenedor hermano los puertos 8888/9333/8080/18888/19333/18080/8181/9101 y el
#   gRPC de 18333 (RemoveIdentity vacio; se espera grpc-status 3).
# Fase 2: recrea sobre el MISMO volumen con -ip/-ip.bind=127.0.0.1 -s3.ip.bind=0.0.0.0, -s3.port.iceberg=0
#   -s3.port.lance=0 (deshabilitan Iceberg REST 8181 y Lance 9101; "0 to disable") y security.toml
#   ([jwt.filer_signing]) y verifica: healthy, listeners, curl exit 7 a los puertos internos,
#   /healthz 200, grpc-status 16 en 18333, DELETE al filer = 401, mismo sha256 del testigo,
#   `pits storage init` (policy=applied) y `pytest -m contract` contra el probe.
# Los 2 e2e contract que cargan a Postgres (fx_rate/vehicle_fleet) se excluyen: el probe no levanta PG.
# Si un criterio de la fase 2 falla, se detiene (sin cambiar flags) y sale con 1.
# Termina siempre con `down -v` del proyecto del probe (trap).
set -euo pipefail
export MSYS_NO_PATHCONV=1

PROJECT="pits-swprobe"
VOLUME="pits_swprobe_data"
NET="${PROJECT}_default"
CNAME="${PROJECT}-seaweedfs"
HOST_PORT="28333"
IMAGE="chrislusf/seaweedfs:4.48@sha256:4e61d15fd35994cb1e43e1e553dff106794841fd9a99ade2fc8c8bfce4d7872d"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-180}"
REGION="us-east-1"
BUCKET="pits-swprobe-witness"
RAW_BUCKET="pits-raw"
NORM_BUCKET="pits-normalized"
CMD_PHASE1='["server", "-s3", "-s3.config=/etc/seaweedfs/s3.json"]'
CMD_PHASE2='["server", "-s3", "-s3.config=/etc/seaweedfs/s3.json", "-ip=127.0.0.1", "-ip.bind=127.0.0.1", "-s3.ip.bind=0.0.0.0", "-s3.port.iceberg=0", "-s3.port.lance=0"]'
INTERNAL_PORTS="8888 9333 8080 18888 19333 18080 8181 9101"
N_INTERNAL=8

cd "$(dirname "$0")/.."

T="$(mktemp -d)"
TW="$T"
if command -v cygpath >/dev/null 2>&1; then TW="$(cygpath -m "$T")"; fi

dc() { docker compose -p "$PROJECT" -f "$TW/compose.yml" --env-file "$TW/probe.env" "$@"; }
cleanup() {
  local rc=$?
  set +e
  echo "## cleanup: down -v del proyecto $PROJECT"
  if [ -f "$T/compose.yml" ]; then dc down -v --remove-orphans >/dev/null 2>&1; fi
  docker volume rm "$VOLUME" >/dev/null 2>&1
  rm -rf "$T"
  exit "$rc"
}
trap cleanup EXIT

if docker volume inspect "$VOLUME" >/dev/null 2>&1; then
  echo "FAIL: ya existe el volumen $VOLUME (restos de otra sonda); bórralo a mano" >&2
  trap - EXIT; rm -rf "$T"; exit 1
fi

rand_hex() { uv run --no-sync python -c "import secrets; print(secrets.token_hex(16).upper())"; }
rand_url() { uv run --no-sync python -c "import secrets; print(secrets.token_urlsafe($1))"; }

ADMIN_KEY="$(rand_hex)";  ADMIN_SECRET="$(rand_url 32)"
WRITER_KEY="$(rand_hex)"; WRITER_SECRET="$(rand_url 32)"
READER_KEY="$(rand_hex)"; READER_SECRET="$(rand_url 32)"
JWT_KEY="$(rand_url 48)"

umask 077
cat >"$T/probe.env" <<EOF
S3_ACCESS_KEY_ID=$ADMIN_KEY
S3_SECRET_ACCESS_KEY=$ADMIN_SECRET
PITS_S3_WRITER_ACCESS_KEY_ID=$WRITER_KEY
PITS_S3_WRITER_SECRET_ACCESS_KEY=$WRITER_SECRET
PITS_S3_READER_ACCESS_KEY_ID=$READER_KEY
PITS_S3_READER_SECRET_ACCESS_KEY=$READER_SECRET
S3_RAW_BUCKET=$RAW_BUCKET
S3_NORMALIZED_BUCKET=$NORM_BUCKET
PROBE_JWT_KEY=$JWT_KEY
EOF

# gen_compose <command_json> <con_security: 0|1>
gen_compose() {
  local cmd="$1" sec="$2"
  {
    cat <<EOF
name: $PROJECT
services:
  seaweedfs:
    image: $IMAGE
    container_name: $CNAME
    command: $cmd
    configs:
      - source: seaweedfs_s3
        target: /etc/seaweedfs/s3.json
EOF
    if [ "$sec" = 1 ]; then
      cat <<'EOF'
      - source: seaweedfs_security
        target: /etc/seaweedfs/security.toml
EOF
    fi
    cat <<EOF
    environment:
      GOMEMLIMIT: 500MiB
    mem_limit: 768m
    memswap_limit: 768m
    ports:
      - "127.0.0.1:$HOST_PORT:8333"
    volumes:
      - seaweedfs_data:/data
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8333/healthz"]
      interval: 5s
      timeout: 5s
      retries: 30
      start_period: 10s
EOF
    cat <<'EOF'
configs:
  seaweedfs_s3:
    content: |
      {
        "identities": [
          {"name": "pits_admin",
           "credentials": [{"accessKey": "${S3_ACCESS_KEY_ID}", "secretKey": "${S3_SECRET_ACCESS_KEY}"}],
           "actions": ["Admin", "Read", "List", "Tagging", "Write"]},
          {"name": "pits_writer",
           "credentials": [{"accessKey": "${PITS_S3_WRITER_ACCESS_KEY_ID}", "secretKey": "${PITS_S3_WRITER_SECRET_ACCESS_KEY}"}],
           "actions": ["Read:${S3_RAW_BUCKET}", "List:${S3_RAW_BUCKET}", "Write:${S3_RAW_BUCKET}",
                       "Read:${S3_NORMALIZED_BUCKET}", "List:${S3_NORMALIZED_BUCKET}", "Write:${S3_NORMALIZED_BUCKET}"]},
          {"name": "pits_reader",
           "credentials": [{"accessKey": "${PITS_S3_READER_ACCESS_KEY_ID}", "secretKey": "${PITS_S3_READER_SECRET_ACCESS_KEY}"}],
           "actions": ["Read:${S3_RAW_BUCKET}", "List:${S3_RAW_BUCKET}",
                       "Read:${S3_NORMALIZED_BUCKET}", "List:${S3_NORMALIZED_BUCKET}"]}
        ]
      }
EOF
    if [ "$sec" = 1 ]; then
      cat <<'EOF'
  seaweedfs_security:
    content: |
      [jwt.filer_signing]
      key = "${PROBE_JWT_KEY}"
EOF
    fi
    cat <<EOF
volumes:
  seaweedfs_data:
    name: $VOLUME
EOF
  } >"$T/compose.yml"
}

wait_healthy() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT))
  until [ "$(docker inspect -f '{{.State.Health.Status}}' "$CNAME" 2>/dev/null || true)" = healthy ]; do
    if [ "$SECONDS" -ge "$deadline" ]; then
      echo "FAIL: $CNAME no llego a healthy en ${HEALTH_TIMEOUT}s" >&2
      docker logs --tail 30 "$CNAME" 2>&1 | grep -viE 'key|secret|token' >&2 || true
      return 1
    fi
    sleep 2
  done
}

# sib <script>: contenedor hermano (misma imagen, con curl) en la red del probe. AK/SK por entorno.
sib() {
  ( export AK="$ADMIN_KEY" SK="$ADMIN_SECRET"
    docker run --rm --network "$NET" -e AK -e SK --entrypoint sh "$IMAGE" -c "$1" )
}

curl_codes() {
  for p in $INTERNAL_PORTS; do
    sib "c=\$(curl -s -o /dev/null -m 3 -w '%{http_code}' http://seaweedfs:$p/) ; echo \"port $p http_code=\$c curl_exit=\$?\"" \
      || true
  done
}

grpc_status() {
  sib "printf '\\000\\000\\000\\000\\000' > /tmp/empty.bin
curl -s -m 5 --http2-prior-knowledge -X POST -H 'content-type: application/grpc' -H 'te: trailers' \
  --data-binary @/tmp/empty.bin -D - -o /dev/null http://seaweedfs:18333/messaging_pb.SeaweedS3IamCache/RemoveIdentity \
  | tr -d '\r' | grep -i '^grpc-status' || echo 'grpc-status: (ausente)'"
}

S3URL="http://seaweedfs:8333"
SIGV4="aws:amz:$REGION:s3"
EMPTY_SHA="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

witness_put() {
  sib "head -c 1048576 /dev/urandom > /tmp/w.bin
sha=\$(sha256sum /tmp/w.bin | cut -d' ' -f1)
b=\$(curl -s -m 20 --aws-sigv4 $SIGV4 --variable %AK --variable %SK --expand-user '{{AK}}:{{SK}}' -H 'x-amz-content-sha256: $EMPTY_SHA' -X PUT -o /dev/null -w '%{http_code}' $S3URL/$BUCKET)
o=\$(curl -s -m 30 --aws-sigv4 $SIGV4 --variable %AK --variable %SK --expand-user '{{AK}}:{{SK}}' -H \"x-amz-content-sha256: \$sha\" -T /tmp/w.bin -o /dev/null -w '%{http_code}' $S3URL/$BUCKET/witness.bin)
echo \"sha256=\$sha bucket_put=\$b object_put=\$o\""
}

witness_get() {
  sib "curl -s -m 30 --aws-sigv4 $SIGV4 --variable %AK --variable %SK --expand-user '{{AK}}:{{SK}}' -H 'x-amz-content-sha256: $EMPTY_SHA' -o /tmp/g.bin -w 'get=%{http_code} ' $S3URL/$BUCKET/witness.bin
echo \"sha256=\$(sha256sum /tmp/g.bin | cut -d' ' -f1)\""
}

# Lista listeners TCP LISTEN del contenedor como "addr:port" (0.0.0.0, 127.0.0.1, ::, ::1 o crudo).
listeners() {
  local f port a laddr
  for f in /proc/net/tcp /proc/net/tcp6; do
    docker exec "$CNAME" cat "$f" | tail -n +2 | while read -r _ laddr _ st _; do
      [ "$st" = "0A" ] || continue
      a="${laddr%%:*}"; port=$((16#${laddr##*:}))
      case "$a" in
        00000000) a="0.0.0.0" ;;
        ????????) a="$((16#${a:6:2})).$((16#${a:4:2})).$((16#${a:2:2})).$((16#${a:0:2}))" ;;
        00000000000000000000000000000000) a="::" ;;
        00000000000000000000000001000000) a="::1" ;;
      esac
      echo "$a:$port"
    done
  done | sort -u
}

fail=0
check() { # check <descripcion> <ok: 0|1>
  if [ "$2" = 1 ]; then echo "  OK   $1"; else echo "  FAIL $1" >&2; fail=1; fi
}

echo "## sonda: proyecto=$PROJECT volumen=$VOLUME puerto=127.0.0.1:$HOST_PORT imagen=${IMAGE##*@}"
echo "## curl sigv4 en la imagen: $(docker run --rm --entrypoint sh "$IMAGE" -c "curl --version | head -1; curl --help all | grep -c -- '--aws-sigv4' | sed 's/^/aws-sigv4 flags: /'" | tr '\n' ' ')"

# ---------------- Fase 1 ----------------
echo "## FASE 1: linea base (command actual)"
gen_compose "$CMD_PHASE1" 0
dc up -d >/dev/null
wait_healthy
echo "healthy"
put_out="$(witness_put)"
echo "witness: ${put_out//sha256=/sha256 = }"
SHA_BEFORE="$(sed -n 's/.*sha256=\([0-9a-f]*\).*/\1/p' <<<"$put_out")"
[[ "$put_out" == *"bucket_put=200 object_put=200" ]] || { echo "FAIL: fase 1 bucket_put/object_put distintos de 200" >&2; exit 1; }
[ -n "$SHA_BEFORE" ] || { echo "FAIL: no se obtuvo sha256 del testigo" >&2; exit 1; }
echo "sha256 antes: $SHA_BEFORE"
echo "listeners fase 1: $(listeners | tr '\n' ' ')"
echo "-- puertos internos desde contenedor hermano (fase 1)"
curl_codes
echo "-- gRPC 18333 RemoveIdentity vacio (fase 1): $(grpc_status) (esperado grpc-status: 3)"

# ---------------- Fase 2 ----------------
echo "## FASE 2: recreate sobre el mismo volumen con -ip.bind=127.0.0.1 y security.toml"
dc stop -t 30 >/dev/null
gen_compose "$CMD_PHASE2" 1
dc up -d --force-recreate >/dev/null
wait_healthy
echo "healthy"

echo "-- listeners"
L="$(listeners)"
echo "$L" | sed 's/^/  /'
open_set="$(grep -E '^(0\.0\.0\.0|::):' <<<"$L" | sed 's/^[^:]*:\+//' | sort -n | tr '\n' ' ')"
loop_bad="$(grep -vE '^(0\.0\.0\.0|::):|^(127\.[0-9.]+|::1):' <<<"$L" || true)"
echo "  abiertos (0.0.0.0/::): $open_set"
check "solo 8333 y 18333 en 0.0.0.0" "$([ "$open_set" = "8333 18333 " ] && echo 1 || echo 0)"
check "resto solo en loopback" "$([ -z "$loop_bad" ] && echo 1 || echo 0)"

echo "-- puertos internos desde contenedor hermano (esperado curl_exit=7)"
out2="$(curl_codes)"
echo "$out2" | sed 's/^/  /'
check "$N_INTERNAL puertos internos con curl exit 7" "$([ "$(grep -c 'curl_exit=7' <<<"$out2")" = "$N_INTERNAL" ] && echo 1 || echo 0)"

hz="$(sib "curl -s -m 5 -o /dev/null -w '%{http_code}' $S3URL/healthz" || true)"
echo "-- /healthz 8333: $hz"
check "/healthz = 200" "$([ "$hz" = 200 ] && echo 1 || echo 0)"

gs="$(grpc_status)"
echo "-- gRPC 18333: $gs"
check "grpc-status: 16" "$([[ "$gs" =~ ^grpc-status:\ *16$ ]] && echo 1 || echo 0)"

del="$(docker exec "$CNAME" curl -s -o /dev/null -m 5 -w '%{http_code}' -X DELETE http://127.0.0.1:8888/swprobe-nonexistent-path || true)"
echo "-- DELETE 127.0.0.1:8888 dentro del contenedor: $del"
check "DELETE al filer = 401" "$([ "$del" = 401 ] && echo 1 || echo 0)"

get_out="$(witness_get)"
SHA_AFTER="$(sed -n 's/.*sha256=\([0-9a-f]*\).*/\1/p' <<<"$get_out")"
echo "-- testigo tras migracion: ${get_out//sha256=/sha256 = }"
echo "sha256 despues: $SHA_AFTER"
check "sha256 testigo igual" "$([ "$SHA_AFTER" = "$SHA_BEFORE" ] && echo 1 || echo 0)"

if [ "$fail" -ne 0 ]; then
  echo "CRITERIO: FAIL (fase 2); detenido sin cambiar flags" >&2
  docker logs --tail 40 "$CNAME" 2>&1 | grep -viE 'key|secret|token' | tail -20 >&2 || true
  exit 1
fi

# Entorno exportado en subshell (fuera de argv) para el CLI y los tests (sin imprimir valores).
run_pits() {
  ( export S3_ENDPOINT_URL="http://127.0.0.1:$HOST_PORT" S3_REGION="$REGION" \
      S3_ACCESS_KEY_ID="$ADMIN_KEY" S3_SECRET_ACCESS_KEY="$ADMIN_SECRET" \
      PITS_S3_WRITER_ACCESS_KEY_ID="$WRITER_KEY" PITS_S3_WRITER_SECRET_ACCESS_KEY="$WRITER_SECRET" \
      PITS_S3_READER_ACCESS_KEY_ID="$READER_KEY" PITS_S3_READER_SECRET_ACCESS_KEY="$READER_SECRET" \
      S3_RAW_BUCKET="$RAW_BUCKET" S3_NORMALIZED_BUCKET="$NORM_BUCKET" S3_CONTRACT_LARGE_MB=128 \
      PITS_SWNET_NETWORK="$NET" PITS_SWNET_HOST=seaweedfs
    "$@" )
}

echo "-- uv run pits storage init"
rc=0; init_out="$(run_pits uv run --no-sync pits storage init 2>&1)" || rc=$?
echo "$init_out" | tail -8 | sed 's/^/  /'
echo "  exit code: $rc"
check "storage init exit 0 y policy=applied" "$([ "$rc" = 0 ] && grep -q 'policy=applied' <<<"$init_out" && echo 1 || echo 0)"

echo "-- uv run pytest -m contract -q (contra el probe)"
rc=0; py_out="$(run_pits uv run --no-sync pytest -m contract -q --deselect tests/contract/test_fx_rate_load_e2e.py --deselect tests/contract/test_vehicle_fleet_load_e2e.py 2>&1)" || rc=$?
echo "$py_out" | { if [ -n "${PROBE_VERBOSE:-}" ]; then tail -150; else tail -8; fi; } | sed 's/^/  /'
echo "  exit code: $rc"
check "pytest -m contract exit 0" "$([ "$rc" = 0 ] && echo 1 || echo 0)"

if [ "$fail" -eq 0 ]; then echo "CRITERIO: OK"; else echo "CRITERIO: FAIL" >&2; exit 1; fi

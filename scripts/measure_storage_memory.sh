#!/usr/bin/env bash
# Mide memoria/OOM de pits-seaweedfs durante CMD (por defecto la suite contract), RUNS veces.
# CMD (opcional) reemplaza la carga medida; por defecto la suite contract.
# CMD se imprime en el log: no incluir secretos en el.
# Cada corrida: restart -> healthy -> reposo -> contract -> memory.peak/OOM/restarts.
# Criterio: todas las corridas verdes, OOMKilled=false, oom_kill=0, RestartCount=0
# y max(memory.peak) < PEAK_LIMIT (85 % de 768 MiB). Exit 1 si no se cumple.
# Valida antes de medir el limite del cgroup (memory/memswap) y GOMEMLIMIT del contenedor.
# Requiere el stack core arriba (docker compose up -d) y .env con S3_*. No imprime el entorno.
# Efectos: reinicia $C y deja buckets pits-contract-* (Object Lock) en el volumen.
set -euo pipefail
export MSYS_NO_PATHCONV=1

C="${C:-pits-seaweedfs}"
RUNS="${RUNS:-3}"
IDLE_SECONDS="${IDLE_SECONDS:-120}"
GAP_SECONDS="${GAP_SECONDS:-180}" # buckets Object Lock COMPLIANCE: >= 3 min entre corridas
PEAK_LIMIT="${PEAK_LIMIT:-684510412}"
EXPECTED_LIMIT="${EXPECTED_LIMIT:-805306368}" # 768 MiB
EXPECTED_GOMEMLIMIT="${EXPECTED_GOMEMLIMIT:-500MiB}" # D63
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-180}"
CMD="${CMD:-uv run --env-file .env pytest -m contract -q -s}"

[[ "$RUNS" =~ ^[1-9][0-9]*$ ]] || { echo "FAIL: RUNS debe ser entero >= 1 (RUNS=$RUNS)" >&2; exit 1; }
for v in IDLE_SECONDS GAP_SECONDS PEAK_LIMIT HEALTH_TIMEOUT; do
  [[ "${!v}" =~ ^[0-9]+$ ]] || { echo "FAIL: $v debe ser entero >= 0 ($v=${!v})" >&2; exit 1; }
done

out=""
trap 'if [ -n "$out" ]; then rm -f "$out"; fi' EXIT

cd "$(dirname "$0")/.."

cg() { docker exec "$C" cat "/sys/fs/cgroup/$1"; }
stat_lines() { docker exec "$C" sh -c 'grep -E "^(anon|file|kernel) " /sys/fs/cgroup/memory.stat'; }
event() { cg memory.events | awk -v k="$1" '$1 == k {print $2}'; }

echo "## cmd: $CMD"
echo "## limits"
limits="$(docker inspect -f '{{.HostConfig.Memory}} {{.HostConfig.MemorySwap}}' "$C")"
echo "memory/memswap: $limits (esperado: $EXPECTED_LIMIT $EXPECTED_LIMIT)"
[ "$limits" = "$EXPECTED_LIMIT $EXPECTED_LIMIT" ] || { echo "FAIL: limite de memoria inesperado" >&2; exit 1; }
gml="$(docker exec "$C" sh -c 'echo $GOMEMLIMIT')"
echo "GOMEMLIMIT=$gml (esperado: $EXPECTED_GOMEMLIMIT)"
[ "$gml" = "$EXPECTED_GOMEMLIMIT" ] || { echo "FAIL: GOMEMLIMIT inesperado" >&2; exit 1; }

fail=0
max_peak=0
declare -a rows

for run in $(seq 1 "$RUNS"); do
  echo "## run $run/$RUNS restart ($(date -u +%T))"
  docker restart "$C" >/dev/null
  deadline=$((SECONDS + HEALTH_TIMEOUT))
  until [ "$(docker inspect -f '{{.State.Health.Status}}' "$C")" = healthy ]; do
    if [ "$SECONDS" -ge "$deadline" ]; then
      echo "FAIL: $C no llego a healthy en ${HEALTH_TIMEOUT}s" >&2
      exit 1
    fi
    sleep 2
  done
  echo "healthy at $(date -u +%T); idle ${IDLE_SECONDS}s"
  sleep "$IDLE_SECONDS"
  echo "idle memory.peak: $(cg memory.peak)"
  echo "idle memory.current: $(cg memory.current)"
  stat_lines

  echo "## run $run contract start $(date -u +%T)"
  rc=0
  out="$(mktemp)"
  bash -c "$CMD" >"$out" 2>&1 || rc=$?
  grep -E "large object|passed|failed|error" "$out" | tail -5 || true
  if [ "$rc" -ne 0 ]; then tail -40 "$out" >&2; fi
  rm -f "$out"; out=""
  echo "contract exit code: $rc ($(date -u +%T))"

  peak="$(cg memory.peak)"
  current="$(cg memory.current)"
  echo "peak: $peak"
  echo "current: $current"
  stat_lines
  echo "memory.events: oom=$(event oom) oom_kill=$(event oom_kill) max=$(event max)"
  oom_kill="$(event oom_kill)"
  oomk="$(docker inspect -f '{{.State.OOMKilled}}' "$C")"
  restarts="$(docker inspect -f '{{.RestartCount}}' "$C")"
  echo "OOMKilled=$oomk RestartCount=$restarts"
  echo "du /data: $(docker exec "$C" du -sh /data)"

  rows+=("$run rc=$rc peak=$peak oom_kill=$oom_kill OOMKilled=$oomk restarts=$restarts")
  [ "$peak" -gt "$max_peak" ] && max_peak="$peak"
  [ "$rc" -eq 0 ] || fail=1
  [ "$oomk" = "false" ] || fail=1
  [ "$oom_kill" -eq 0 ] || fail=1
  [ "$restarts" -eq 0 ] || fail=1

  if [ "$run" -lt "$RUNS" ]; then sleep "$GAP_SECONDS"; fi
done

echo "## summary"
printf '%s\n' "${rows[@]}"
echo "max(memory.peak)=$max_peak limit=$PEAK_LIMIT"
[ "$max_peak" -lt "$PEAK_LIMIT" ] || fail=1
if [ "$fail" -eq 0 ]; then echo "CRITERIO: OK"; else echo "CRITERIO: FAIL" >&2; exit 1; fi

#!/usr/bin/env bash
# Dispara un DAG de Airflow y espera su estado final (D92). Uso:
#   scripts/run_dag_and_wait.sh <dag_id> [conf-json]
# Exit: 0 = success, 1 = failed (o error al disparar/consultar), 2 = timeout.
# OJO: en timeout (exit 2) la corrida NO se cancela: sigue viva en Airflow y, con
# max_active_runs=1, bloquea las siguientes hasta que termine.
# Variables: SCHEDULER (pits-airflow-scheduler), TIMEOUT_SECONDS (900), POLL_SECONDS (5),
# LOGICAL_DATE (opcional, ISO 8601; sin el, el run manual no tiene logical_date).
# Sirve como CMD de scripts/measure_storage_memory.sh. conf-json no debe llevar secretos: se
# imprime el run_id, nunca el conf ni el entorno. Efecto: crea un DagRun manual en el stack.
set -euo pipefail
export MSYS_NO_PATHCONV=1

SCHEDULER="${SCHEDULER:-pits-airflow-scheduler}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-900}"
POLL_SECONDS="${POLL_SECONDS:-5}"

[ "$#" -ge 1 ] && [ "$#" -le 2 ] || { echo "usage: $0 <dag_id> [conf-json]" >&2; exit 1; }
dag_id="$1"
conf="${2-}"
[[ "$dag_id" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "FAIL: invalid dag_id" >&2; exit 1; }
for v in TIMEOUT_SECONDS POLL_SECONDS; do
  [[ "${!v}" =~ ^[1-9][0-9]*$ ]] || { echo "FAIL: $v must be an integer >= 1" >&2; exit 1; }
done

# The Airflow CLI prints graphviz warnings on stdout: the JSON is the line that starts with "[".
# Parsed inside the scheduler container (its Python is guaranteed; the host's is not).
PARSE='
import json, sys
for line in sys.stdin:
    if line.startswith("["):
        runs = json.loads(line)
        break
else:
    sys.exit(3)
run_id = sys.argv[1]
print(next((r["state"] for r in runs if r["run_id"] == run_id), "unknown"))
'

run_id="manual__it_$(date -u +%Y%m%dT%H%M%S)_$$"
args=(dags trigger -o json -r "$run_id")
[ -n "$conf" ] && args+=(-c "$conf")
[ -n "${LOGICAL_DATE-}" ] && args+=(-l "$LOGICAL_DATE")
err="$(mktemp)"
trap 'rm -f "$err"' EXIT
if ! docker exec "$SCHEDULER" airflow "${args[@]}" "$dag_id" >/dev/null 2>"$err"; then
  echo "FAIL: could not trigger $dag_id: $(tail -n 1 "$err")" >&2
  exit 1
fi
echo "triggered dag_id=$dag_id run_id=$run_id"

deadline=$((SECONDS + TIMEOUT_SECONDS))
state="unknown"
while :; do
  if out="$(docker exec "$SCHEDULER" airflow dags list-runs -o json "$dag_id" 2>/dev/null)"; then
    state="$(printf '%s\n' "$out" | docker exec -i "$SCHEDULER" python -c "$PARSE" "$run_id" || echo unknown)"
  fi
  case "$state" in
    success) echo "state=success run_id=$run_id"; exit 0 ;;
    failed) echo "state=failed run_id=$run_id" >&2; exit 1 ;;
  esac
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "TIMEOUT: $dag_id run_id=$run_id state=$state after ${TIMEOUT_SECONDS}s" >&2
    exit 2
  fi
  sleep "$POLL_SECONDS"
done

#!/usr/bin/env bash
# Generates traffic so Grafana/Prometheus graphs are not empty.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

API_URL="${API_URL:-http://localhost:8001}"
ES_URL="${ES_HOST_LOCAL:-http://localhost:9200}"
PROM_URL="http://localhost:${PROMETHEUS_HOST_PORT:-9090}"
GRAFANA_URL="http://localhost:${GRAFANA_HOST_PORT:-3000}"
CADVISOR_URL="http://localhost:${CADVISOR_HOST_PORT:-8080}"
DURATION="${LOADGEN_DURATION:-90}"
CONCURRENCY="${LOADGEN_CONCURRENCY:-4}"

hit() {
  local timeout="${2:-5}"
  curl -sS -o /dev/null -w "%{http_code} %{time_total}s  %{url}\n" \
    --max-time "$timeout" "$@" || true
}

echo "Waiting for API at ${API_URL}/health ..."
for _ in $(seq 1 30); do
  if curl -sf --max-time 3 "${API_URL}/health" >/dev/null; then
    break
  fi
  sleep 2
done
curl -sf --max-time 5 "${API_URL}/health" >/dev/null \
  || { echo "API is not ready. Run: make up"; exit 1; }

echo
echo "Loadgen ${DURATION}s, ${CONCURRENCY} workers"
echo "  Grafana:    ${GRAFANA_URL}  (SRE → SRE LLM Assistant)"
echo "  Prometheus: ${PROM_URL}/graph"
echo

END="$(($(date +%s) + DURATION))"

worker() {
  local id="$1"
  while [[ "$(date +%s)" -lt "$END" ]]; do
    hit "${API_URL}/health"
    hit "${API_URL}/"
    hit "${API_URL}/metrics"
    hit "${API_URL}/docs"
    hit "${API_URL}/no-such-route"
    curl -sS -o /dev/null -w "%{http_code} %{time_total}s  POST /analyze (422)\n" \
      --max-time 5 -X POST "${API_URL}/api/v1/analyze" \
      -H "Content-Type: application/json" \
      -d '{"hours": 1, "limit": 999}' || true
    hit "${ES_URL}/_cluster/health"
    hit "${PROM_URL}/-/healthy"
    hit "${GRAFANA_URL}/api/health"
    hit "${CADVISOR_URL}/healthz"
    sleep "0.$(printf '%d' "$id")"
  done
}

analyze_loop() {
  while [[ "$(date +%s)" -lt "$END" ]]; do
    echo "POST ${API_URL}/api/v1/analyze (LLM, may take a while)"
    curl -sS -o /dev/null -w "%{http_code} %{time_total}s  POST /analyze\n" \
      --max-time "${LLM_TIMEOUT_SECONDS:-120}" \
      -X POST "${API_URL}/api/v1/analyze" \
      -H "Content-Type: application/json" \
      -d '{"hours": 1, "limit": 10}' || true
    sleep 15
  done
}

pids=()
for i in $(seq 1 "$CONCURRENCY"); do
  worker "$i" &
  pids+=("$!")
done
analyze_loop &
pids+=("$!")

cleanup() {
  kill "${pids[@]}" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM

wait "${pids[@]}" || true
echo
echo "Done. Open ${GRAFANA_URL} and wait ~15s for scrape."

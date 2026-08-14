#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

IMAGE="${SRE_API_IMAGE:-}"
if [[ -z "$IMAGE" ]]; then
  echo "SRE_API_IMAGE is required, e.g. ghcr.io/owner/sre-llm-assistant/sre-api:<sha>"
  exit 1
fi

export SRE_API_IMAGE="$IMAGE"
HEALTH_URL="${API_URL:-http://localhost:${API_HOST_PORT:-8001}}/health"

if [[ -n "${GHCR_TOKEN:-}" ]]; then
  echo "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_USER:-github}" --password-stdin
fi

echo "Deploying ${SRE_API_IMAGE}..."
docker compose pull sre-api
docker compose up -d --no-build

if docker exec ollama ollama list >/dev/null 2>&1; then
  docker exec ollama ollama pull "${OLLAMA_MODEL}"
fi

echo "Waiting for API health at ${HEALTH_URL}..."
for _ in $(seq 1 60); do
  if curl -sf "${HEALTH_URL}" >/dev/null; then
    echo "API is healthy"
    docker compose ps
    exit 0
  fi
  sleep 5
done

echo "API did not become healthy"
docker compose ps
docker compose logs --tail=80 sre-api
exit 1

#!/bin/bash
set -e

ES_HOST="${ES_HOST:-http://opensearch:9200}"
API_PORT="${API_PORT:-8000}"

echo "Waiting for OpenSearch..."
until curl -sf "${ES_HOST}/_cluster/health" > /dev/null; do
  echo "  still waiting..."
  sleep 5
done
echo "OpenSearch is ready."

echo "Starting SRE API on :${API_PORT}..."
exec uvicorn src.main:app --host 0.0.0.0 --port "${API_PORT}"

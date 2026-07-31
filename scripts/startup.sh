#!/bin/bash
set -e

echo "⏳ Waiting for OpenSearch..."
until curl -sf "${ES_HOST:-http://opensearch:9200}/_cluster/health" > /dev/null; do
  echo "  → still waiting..."
  sleep 5
done
echo "✅ OpenSearch ready."

# Индекс и сиды выполняются с хоста (make/CI). Здесь только поднимаем API.
echo "🚀 Starting SRE API on :8000..."
exec uvicorn src.main:app --host 0.0.0.0 --port 8000

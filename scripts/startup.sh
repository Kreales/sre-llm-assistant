#!/bin/bash
set -e

echo "Waiting for OpenSearch..."
until curl -sf "${ES_HOST:-http://opensearch:9200}/_cluster/health" > /dev/null; do
  echo "  still waiting..."
  sleep 5
done
echo "OpenSearch is ready."

# Index template and seed run from the host (make/CI). Here we only start the API.
echo "Starting SRE API on :8000..."
exec uvicorn src.main:app --host 0.0.0.0 --port 8000

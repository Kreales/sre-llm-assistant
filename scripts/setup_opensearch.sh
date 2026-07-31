#!/bin/bash
set -e

ES_URL="${ES_HOST:-http://localhost:9200}"

echo "⏳ Waiting for OpenSearch at ${ES_URL}..."
for i in $(seq 1 60); do
  if curl -sf --connect-timeout 5 "${ES_URL}/_cluster/health" > /dev/null; then
    echo "✅ OpenSearch ready."
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "❌ OpenSearch not ready"
    exit 1
  fi
  sleep 2
done

CURRENT_DATE=$(date +%Y.%m.%d)
INDEX_NAME="sre-logs-${CURRENT_DATE}"

echo "Deleting existing index: ${INDEX_NAME}"
curl -sf -X DELETE "${ES_URL}/${INDEX_NAME}" > /dev/null 2>&1 || true

echo "🔧 Creating Index Template with proper keyword fields..."

curl -sf -X PUT "${ES_URL}/_index_template/sre-logs-template" \
  -H 'Content-Type: application/json' \
  -d '{
    "index_patterns": ["sre-logs-*"],
    "template": {
      "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "index.refresh_interval": "1s"
      },
      "mappings": {
        "properties": {
          "@timestamp": { "type": "date" },
          "level": {
            "type": "text",
            "fields": {
              "keyword": { "type": "keyword", "ignore_above": 256 }
            }
          },
          "service": {
            "type": "text",
            "fields": {
              "keyword": { "type": "keyword", "ignore_above": 256 }
            }
          },
          "pod": {
            "type": "text",
            "fields": {
              "keyword": { "type": "keyword", "ignore_above": 256 }
            }
          },
          "message": {
            "type": "text",
            "fields": {
              "keyword": { "type": "keyword", "ignore_above": 1024 }
            }
          },
          "host": {
            "type": "text",
            "fields": {
              "keyword": { "type": "keyword", "ignore_above": 256 }
            }
          }
        }
      }
    }
  }'

echo ""
echo "✅ Index Template created."
curl -s "${ES_URL}/_cat/indices?v" | head -n 5

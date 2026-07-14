#!/bin/bash

echo "⏳ Waiting for OpenSearch..."
sleep 10

if ! curl -s --connect-timeout 5 http://localhost:9200/_cluster/health > /dev/null; then
  echo "❌ OpenSearch not ready"
  exit 1
fi

echo "🔧 Creating Index Template with proper keyword fields..."

curl -X PUT "http://localhost:9200/_index_template/sre-logs-template" \
  -H 'Content-Type: application/json' \
  -d '{
    "index_patterns": ["sre-logs-*"],
    "template": {
      "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "index.refresh_interval": "5s"
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
          "message": { "type": "text" },
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

echo "✅ Index Template created."
curl -s "http://localhost:9200/_cat/indices?v" | head -n 5

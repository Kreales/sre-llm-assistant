#!/bin/bash

# Ждём пока OpenSearch поднимется
sleep 30

# Применяем настройки индекса через API
curl -X PUT "http://localhost:9200/_all/_settings?preserve_existing=true" -H 'Content-Type: application/json' -d '{
  "index.refresh_interval": "60s"
}'

# Создаём index template для логов
curl -X PUT "http://localhost:9200/_index_template/sre-logs-template" -H 'Content-Type: application/json' -d '{
  "index_patterns": ["sre-logs-*"],
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 0,
      "refresh_interval": "60s"
    }
  }
}'

echo "Index settings applied!"

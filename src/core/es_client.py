# src/core/es_client.py
import os
import logging
from opensearchpy import OpenSearch

logger = logging.getLogger(__name__)


class OpenSearchClient:
    def __init__(self, host: str | None = None):
        host = host or os.getenv("ES_HOST", "http://opensearch:9200")
        self.client = OpenSearch(
            hosts=[host],
            timeout=10,
            retry_on_timeout=True,
            max_retries=3,
        )

    def get_error_logs(self, minutes: int = 60, limit: int = 30) -> list:
        """Возвращает до `limit` ERROR/CRITICAL логов за последние `minutes` минут."""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "range": {
                                "@timestamp": {
                                    "gte": f"now-{minutes}m/m"
                                }
                            }
                        },
                        {
                            "terms": {
                                "level.keyword": ["ERROR", "CRITICAL"]
                            }
                        },
                    ]
                }
            },
            "sort": [{"@timestamp": {"order": "desc"}}],
            "size": limit,
        }

        try:
            resp = self.client.search(index="sre-logs-*", body=query)
            logs = [hit["_source"] for hit in resp["hits"]["hits"]]
            print(f"🔍 Found {len(logs)} error logs for analysis")
            return logs
        except Exception as e:
            logger.error(f"OpenSearch query failed: {e}")
            return []

    def get_error_groups(self, minutes: int = 60, top_k: int = 3) -> list:
        """Возвращает топ-K групп ошибок с примерами логов."""
        query = {
            "size": 0,
            "query": {
                "bool": {
                    "must": [
                        {"range": {"@timestamp": {"gte": f"now-{minutes}m/m"}}},
                        {"terms": {"level.keyword": ["ERROR", "CRITICAL"]}},
                    ]
                }
            },
            "aggs": {
                "by_message": {
                    "terms": {
                        "field": "message.keyword",
                        "size": top_k,
                        "order": {"_count": "desc"},
                    },
                    "aggs": {
                        "sample_logs": {
                            "top_hits": {
                                "size": 5,
                                "_source": ["@timestamp", "service", "pod", "message", "level"],
                            }
                        }
                    },
                }
            },
        }

        try:
            resp = self.client.search(index="sre-logs-*", body=query)
            buckets = resp["aggregations"]["by_message"]["buckets"]

            groups = []
            for bucket in buckets:
                groups.append(
                    {
                        "message": bucket["key"],
                        "count": bucket["doc_count"],
                        "samples": [
                            hit["_source"]
                            for hit in bucket["sample_logs"]["hits"]["hits"]
                        ],
                    }
                )
            return groups
        except Exception as e:
            logger.error(f"Error fetching error groups: {e}")
            return []

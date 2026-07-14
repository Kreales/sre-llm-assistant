# src/core/es_client.py
from opensearchpy import OpenSearch
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class OpenSearchClient:
    def __init__(self, host: str = "http://opensearch:9200"):
        self.client = OpenSearch(
            hosts=[host],
            timeout=10,
            retry_on_timeout=True,
            max_retries=3
        )

    def get_error_logs(self, minutes: int = 60, limit: int = 50) -> list:
        """Получает логи уровня ERROR/CRITICAL за последние минуты"""
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
                            "simple_query_string": {
                                "query": 'level:(ERROR OR CRITICAL)',
                                "fields": ["level"]
                            }
                        }
                    ]
                }
            },
            "sort": [{"@timestamp": {"order": "desc"}}],
            "size": limit
        }

        try:
            resp = self.client.search(index="sre-logs-*", body=query)
            return [hit["_source"] for hit in resp["hits"]["hits"]]
        except Exception as e:
            logger.error(f"OpenSearch query failed: {e}")
            return []   

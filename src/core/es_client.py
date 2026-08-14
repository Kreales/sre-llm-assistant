import logging

from opensearchpy import OpenSearch

from src.core.config import settings

logger = logging.getLogger(__name__)


class OpenSearchClient:
    def __init__(self, host: str | None = None):
        host = host or settings.es_host
        self.index = settings.es_index_pattern
        self.client = OpenSearch(
            hosts=[host],
            timeout=10,
            retry_on_timeout=True,
            max_retries=3,
        )

    def get_error_logs(self, minutes: int = 60, limit: int = 10) -> list:
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
            resp = self.client.search(index=self.index, body=query)
            logs = [hit["_source"] for hit in resp["hits"]["hits"]]
            logger.info("Found %s error logs for analysis", len(logs))
            return logs
        except Exception as e:
            logger.error("OpenSearch query failed: %s", e)
            return []

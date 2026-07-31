from unittest.mock import patch
from src.core.es_client import OpenSearchClient


@patch("src.core.es_client.OpenSearch")
def test_get_error_logs_success(mock_os):
    mock_resp = {
        "hits": {
            "hits": [
                {"_source": {"level": "ERROR", "message": "Test error"}},
                {"_source": {"level": "CRITICAL", "message": "Critical issue"}},
            ]
        }
    }
    mock_os.return_value.search.return_value = mock_resp

    client = OpenSearchClient()
    logs = client.get_error_logs(minutes=10, limit=10)

    assert len(logs) == 2
    assert logs[0]["level"] == "ERROR"
    assert logs[1]["level"] == "CRITICAL"

    _, kwargs = mock_os.return_value.search.call_args
    assert kwargs["body"]["size"] == 10
    assert kwargs["index"] == "sre-logs-*"


@patch("src.core.es_client.OpenSearch")
def test_get_error_groups_success(mock_os):
    mock_resp = {
        "aggregations": {
            "by_message": {
                "buckets": [
                    {
                        "key": "Connection refused",
                        "doc_count": 5,
                        "sample_logs": {
                            "hits": {
                                "hits": [
                                    {
                                        "_source": {
                                            "message": "Connection refused",
                                            "service": "api",
                                        }
                                    },
                                    {
                                        "_source": {
                                            "message": "Connection refused",
                                            "service": "api",
                                        }
                                    },
                                ]
                            }
                        },
                    }
                ]
            }
        }
    }
    mock_os.return_value.search.return_value = mock_resp

    client = OpenSearchClient()
    groups = client.get_error_groups(minutes=10, top_k=3)

    assert len(groups) == 1
    assert groups[0]["count"] == 5
    assert len(groups[0]["samples"]) == 2

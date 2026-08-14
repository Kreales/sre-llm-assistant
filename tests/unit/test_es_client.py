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

from unittest.mock import patch
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


@patch("src.api.analyze.llm.generate_remediation")
@patch("src.api.analyze.es.get_error_logs")
def test_analyze_endpoint_returns_json(mock_get_logs, mock_llm):
    mock_get_logs.return_value = [
        {
            "@timestamp": "2026-07-31T10:00:00Z",
            "level": "ERROR",
            "service": "auth-service",
            "pod": "auth-1",
            "message": "Connection refused",
        },
        {
            "@timestamp": "2026-07-31T10:01:00Z",
            "level": "CRITICAL",
            "service": "payment-gateway",
            "pod": "pay-1",
            "message": "OOMKilled",
        },
        {
            "@timestamp": "2026-07-31T10:02:00Z",
            "level": "ERROR",
            "service": "auth-service",
            "pod": "auth-2",
            "message": "Connection refused",
        },
    ]
    mock_llm.return_value = {
        "issues": [
            {
                "error": "Connection refused",
                "root_cause": "db down",
                "risk": "high",
                "commands": ["kubectl get pods"],
            },
            {
                "error": "OOMKilled",
                "root_cause": "memory",
                "risk": "medium",
                "commands": ["kubectl top pod"],
            },
        ],
        "summary": "two issues",
        "priority_order": ["Connection refused", "OOMKilled"],
    }

    response = client.post("/api/v1/analyze", json={"hours": 0.1})
    assert response.status_code == 200
    data = response.json()
    assert data["logs_analyzed"] == 3
    assert data["unique_errors"] == 2
    assert len(data["error_summary"]) == 2

    sent_errors = mock_llm.call_args[0][0]
    assert len(sent_errors) == 2
    assert sent_errors[0]["message"] == "Connection refused"
    assert sent_errors[0]["count"] == 2
    assert sent_errors[1]["message"] == "OOMKilled"


@patch("src.api.analyze.es.get_error_logs")
def test_analyze_no_logs(mock_get_logs):
    mock_get_logs.return_value = []
    response = client.post("/api/v1/analyze", json={"hours": 1})
    assert response.status_code == 200
    assert response.json()["status"] == "no_logs"

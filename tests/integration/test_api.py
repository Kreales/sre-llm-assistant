import pytest
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
            "message": "Connection refused",
        },
        {
            "@timestamp": "2026-07-31T10:01:00Z",
            "level": "CRITICAL",
            "service": "payment-gateway",
            "message": "OOMKilled",
        },
    ]
    mock_llm.return_value = {
        "root_cause": "test",
        "commands": ["kubectl get pods"],
        "risk": "medium",
        "explanation": "test explanation",
    }

    response = client.post("/api/v1/analyze", json={"hours": 0.1})
    assert response.status_code == 200
    data = response.json()
    assert "request" in data
    assert data["logs_analyzed"] == 2
    assert "remediation" in data

    # В LLM уходят оба лога, а не только первый
    sent_text = mock_llm.call_args[0][0]
    assert "Connection refused" in sent_text
    assert "OOMKilled" in sent_text


@patch("src.api.analyze.es.get_error_logs")
def test_analyze_no_logs(mock_get_logs):
    mock_get_logs.return_value = []
    response = client.post("/api/v1/analyze", json={"hours": 1})
    assert response.status_code == 200
    assert response.json()["status"] == "no_logs"

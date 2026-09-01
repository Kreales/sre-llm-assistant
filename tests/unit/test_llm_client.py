from unittest.mock import patch

from src.core.llm_client import LLMClient


def test_normalize_fills_missing_fields():
    client = LLMClient()
    result = client._normalize_remediation(
        {
            "issues": [
                {"error": "OOMKilled"},
                {"error": "DB down", "risk": "CRITICAL", "commands": "restart"},
            ]
        }
    )

    assert len(result["issues"]) == 2
    assert result["issues"][0]["root_cause"]
    assert result["issues"][0]["risk"] == "medium"
    assert isinstance(result["issues"][0]["commands"], list)
    assert result["issues"][0]["commands"]
    assert result["issues"][1]["risk"] == "medium"
    assert result["issues"][1]["commands"] == ["restart"]
    assert isinstance(result["summary"], str) and result["summary"]
    assert result["priority_order"] == ["OOMKilled", "DB down"]


def test_normalize_replaces_placeholder_priority():
    client = LLMClient()
    result = client._normalize_remediation(
        {
            "issues": [
                {
                    "error": "timeout",
                    "root_cause": "сеть",
                    "risk": "high",
                    "commands": ["curl -v svc"],
                }
            ],
            "summary": "ok",
            "priority_order": ["ошибка с высшим приоритетом"],
        }
    )
    assert result["priority_order"] == ["timeout"]


def test_normalize_keeps_complete_payload():
    client = LLMClient()
    payload = {
        "issues": [
            {
                "error": "timeout",
                "root_cause": "сеть",
                "risk": "high",
                "commands": ["curl -v svc", "kubectl logs pod"],
            }
        ],
        "summary": "таймауты",
        "priority_order": ["timeout"],
    }
    assert client._normalize_remediation(payload) == payload


def test_generate_remediation_returns_fallback_on_llm_failure():
    client = LLMClient()
    errors = [
        {
            "message": "Connection refused",
            "count": 2,
            "level": "ERROR",
            "service": "auth-service",
            "pod": "auth-1",
        }
    ]

    with patch.object(client, "_call_ollama", return_value=("", "LLM timeout after 60s")):
        result = client.generate_remediation(errors)

    assert len(result["issues"]) == 1
    assert result["issues"][0]["error"] == "Connection refused"
    assert result["issues"][0]["risk"] == "medium"
    assert result["issues"][0]["commands"]
    assert isinstance(result["summary"], str)
    assert result["priority_order"] == ["Connection refused"]


def test_generate_remediation_validates_llm_response():
    client = LLMClient()
    errors = [
        {
            "message": "OOMKilled",
            "count": 1,
            "level": "CRITICAL",
            "service": "payment",
            "pod": "pay-1",
        }
    ]
    llm_json = (
        '{"error": "OOMKilled", "root_cause": "Контейнер превысил лимит памяти 512Mi и был завершён OOMKiller.", '
        '"risk": "high", "commands": ["kubectl top pod pay-1", "kubectl describe pod pay-1"]}'
    )

    with patch.object(client, "_call_ollama", return_value=(llm_json, None)):
        result = client.generate_remediation(errors)

    assert result["issues"][0]["error"] == "OOMKilled"
    assert result["issues"][0]["risk"] == "high"
    assert len(result["issues"][0]["commands"]) == 2
    assert "OOMKilled" in result["summary"]
    assert result["priority_order"][0] == "OOMKilled"


def test_quality_issue_rejects_placeholder_commands():
    client = LLMClient()
    issue = {
        "error": "timeout",
        "root_cause": "Сервис payment-gateway не отвечает из-за перегрузки upstream.",
        "risk": "medium",
        "commands": [
            "curl payment-gateway-url?param1=value1",
            "kubectl logs pay-1",
        ],
    }
    assert client._quality_issue(issue, "timeout") == "команды содержат плейсхолдеры"


def test_infer_risk_for_oom_and_critical():
    client = LLMClient()
    assert client._infer_risk("OOMKilled: limit", "ERROR", "low") == "high"
    assert client._infer_risk("Timeout upstream", "CRITICAL", "low") == "high"
    assert client._infer_risk("Minor warning", "ERROR", "low") == "medium"


def test_build_priority_order_sorts_by_risk():
    client = LLMClient()
    issues = [
        {"error": "low issue", "risk": "low"},
        {"error": "high issue", "risk": "high"},
        {"error": "medium issue", "risk": "medium"},
    ]
    assert client._build_priority_order(issues) == [
        "high issue",
        "medium issue",
        "low issue",
    ]


def test_parse_json_response_extracts_object():
    client = LLMClient()
    parsed = client._parse_json_response('prefix {"error": "x", "risk": "low"} suffix')
    assert parsed["error"] == "x"

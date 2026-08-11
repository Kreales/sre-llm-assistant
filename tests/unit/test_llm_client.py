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

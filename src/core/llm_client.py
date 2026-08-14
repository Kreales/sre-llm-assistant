import httpx
import json
import re
import logging
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from src.core.config import settings

logger = logging.getLogger(__name__)


class IssueItem(BaseModel):
    error: str = Field(description="Текст ошибки из логов")
    root_cause: str = Field(description="Причина и предложение по исправлению на русском")
    risk: str = Field(description="low, medium или high")
    commands: List[str] = Field(description="2-3 CLI-команды для диагностики/исправления")


class RemediationResponse(BaseModel):
    issues: List[IssueItem] = Field(description="По одной записи на каждую уникальную ошибку")
    summary: str = Field(description="1-2 предложения — общая картина инцидента")
    priority_order: List[str] = Field(
        description="Тексты ошибок в порядке приоритета устранения"
    )


REMEDIATION_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "error": {"type": "string"},
                    "root_cause": {"type": "string"},
                    "risk": {"type": "string"},
                    "commands": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["error", "root_cause", "risk", "commands"],
            },
        },
        "summary": {"type": "string"},
        "priority_order": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["issues", "summary", "priority_order"],
}


class LLMClient:
    def __init__(self, host: str | None = None, model: str | None = None):
        self.host = (host or settings.ollama_host).rstrip("/")
        self.model = model or settings.ollama_model
        self.timeout = settings.llm_timeout_seconds

    def generate_remediation(self, logs_text: str) -> Dict[str, Any]:
        """
        Запрашивает у LLM анализ логов и рекомендации.
        Возвращает словарь с полями issues/summary/priority_order или {"error": "..."}.
        """
        system_prompt = (
            "Ты — опытный SRE-инженер. "
            "Учти ВСЕ уникальные ошибки из списка. Не выдумывай факты. "
            "Ответ — только валидный JSON по схеме."
        )

        user_prompt = (
            f"{logs_text}\n\n"
            "Верни JSON с полями issues, summary, priority_order.\n"
            "Каждый элемент issues ОБЯЗАН содержать: error, root_cause, risk, commands.\n"
            "risk только: low, medium или high.\n"
            "commands — массив из 2-3 реальных CLI-команд.\n"
            "priority_order — те же тексты error, от критичного к менее важному.\n"
            "Без markdown и текста вне JSON."
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": REMEDIATION_SCHEMA,
            "options": {
                "temperature": 0,
                "top_k": 20,
                "top_p": 0.8,
                "num_ctx": 4096,
                "num_predict": 1024,
            },
        }

        logger.info(
            "LLM request: model=%s prompt_chars=%s",
            self.model,
            len(user_prompt),
        )

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.host}/api/chat", json=payload)

                # Старые Ollama без schema в format — fallback на format=json
                if response.status_code == 400 and "format" in response.text.lower():
                    payload["format"] = "json"
                    response = client.post(f"{self.host}/api/chat", json=payload)

                if response.status_code == 404:
                    return {
                        "error": (
                            f"Endpoint not found at {self.host}/api/chat. "
                            "Is Ollama running with correct model?"
                        )
                    }
                if response.status_code == 400:
                    return {"error": f"Bad request to LLM: {response.text}"}
                if response.status_code != 200:
                    return {
                        "error": (
                            f"LLM request failed with status "
                            f"{response.status_code}: {response.text}"
                        )
                    }

                result = response.json()
                raw_response = result.get("message", {}).get("content", "")

                if not raw_response:
                    return {"error": "LLM returned empty response", "raw": result}

                parsed = self._parse_json_response(raw_response)
                if "error" in parsed and "issues" not in parsed:
                    return parsed
                return self._normalize_remediation(parsed)

        except httpx.TimeoutException:
            logger.error("LLM request timed out to %s", self.host)
            return {"error": f"LLM timeout after {int(self.timeout)}s"}
        except httpx.RequestError as e:
            logger.error(f"LLM request error: {e}")
            return {"error": f"LLM request error: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected error during LLM request: {e}")
            return {"error": f"Unexpected error: {str(e)}"}

    def _normalize_remediation(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Гарантирует наличие всех обязательных полей в ответе LLM."""
        issues_raw = data.get("issues")
        if not isinstance(issues_raw, list):
            # Иногда модель кладёт одну issue на верхний уровень
            if any(k in data for k in ("error", "root_cause", "commands")):
                issues_raw = [data]
            else:
                issues_raw = []

        issues: List[Dict[str, Any]] = []
        for item in issues_raw:
            if not isinstance(item, dict):
                continue
            risk = str(item.get("risk") or "medium").lower().strip()
            if risk not in {"low", "medium", "high"}:
                risk = "medium"
            commands = item.get("commands") or []
            if isinstance(commands, str):
                commands = [commands]
            if not isinstance(commands, list):
                commands = []
            commands = [str(c) for c in commands if c][:3]

            issues.append(
                {
                    "error": str(item.get("error") or item.get("message") or "unknown"),
                    "root_cause": str(
                        item.get("root_cause")
                        or item.get("cause")
                        or item.get("recommendation")
                        or "Не удалось определить причину по логам"
                    ),
                    "risk": risk,
                    "commands": commands
                    or ["kubectl get pods -A", "kubectl describe pod <pod>"],
                }
            )

        summary = data.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            if issues:
                summary = f"Обнаружено ошибок: {len(issues)}. Требуется проверка по приоритету."
            else:
                summary = "Не удалось сформировать итог по логам."

        issue_errors = [i["error"] for i in issues]
        priority = data.get("priority_order")
        placeholder_hints = ("ошибка с высшим приоритетом", "...", "текст ошибки")
        if not isinstance(priority, list) or not priority:
            priority = issue_errors
        else:
            priority = [str(p) for p in priority if p]
            # gemma иногда копирует пример из промпта — тогда берём реальные ошибки
            if any(any(h in p.lower() for h in placeholder_hints) for p in priority):
                priority = issue_errors
            elif issue_errors and not any(
                any(err in p or p in err for err in issue_errors) for p in priority
            ):
                priority = issue_errors

        return {
            "issues": issues,
            "summary": summary.strip(),
            "priority_order": priority,
        }

    def _parse_json_response(self, raw_response: str) -> Dict[str, Any]:
        start_pos = raw_response.find("{")
        if start_pos == -1:
            return {
                "error": "No JSON object found in LLM response",
                "raw_response_snippet": raw_response[:200],
            }

        bracket_count = 0
        end_pos = -1
        for i, char in enumerate(raw_response[start_pos:], start=start_pos):
            if char == "{":
                bracket_count += 1
            elif char == "}":
                bracket_count -= 1
                if bracket_count == 0:
                    end_pos = i
                    break

        if end_pos != -1:
            json_str = raw_response[start_pos : end_pos + 1]
        else:
            json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            if not json_match:
                return {
                    "error": "LLM did not return valid JSON format",
                    "raw_response_snippet": raw_response[:200] + "...",
                }
            json_str = json_match.group()

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            try:
                return json.loads(json_str.replace("'", '"'))
            except json.JSONDecodeError:
                return {
                    "error": "Could not parse JSON from LLM response",
                    "raw_response_snippet": raw_response[:200] + "...",
                }

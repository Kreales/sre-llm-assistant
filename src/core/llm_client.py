import httpx
import json
import logging
import re
import time
from typing import Any, Dict, List

from pydantic import BaseModel, Field, ValidationError

from src.core.config import settings

logger = logging.getLogger(__name__)

RISK_ORDER = {"high": 0, "medium": 1, "low": 2}
PLACEHOLDER_MARKERS = (
    "<pod>",
    "<namespace>",
    "param1",
    "param2",
    "example",
    "payment-gateway-url",
    "...",
    "your-",
    "todo",
)


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


SINGLE_ISSUE_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {"type": "string"},
        "root_cause": {"type": "string"},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "commands": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 3,
        },
    },
    "required": ["error", "root_cause", "risk", "commands"],
}

REMEDIATION_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": SINGLE_ISSUE_SCHEMA,
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
        self.per_call_timeout = settings.llm_per_call_timeout_seconds
        self.max_retries = settings.llm_max_retries

    def generate_remediation(self, errors: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Анализирует каждую ошибку отдельным запросом к LLM.
        Короткие ответы стабильнее и быстрее на CPU-only системах.
        """
        if not errors:
            return {
                "issues": [],
                "summary": "Уникальные ошибки для анализа не найдены.",
                "priority_order": [],
            }

        started = time.monotonic()
        issues: List[Dict[str, Any]] = []

        for error in errors:
            elapsed = time.monotonic() - started
            remaining_budget = self.timeout - elapsed
            if remaining_budget < 5:
                logger.warning(
                    "LLM time budget exhausted after %.1fs, using fallback for remaining errors",
                    elapsed,
                )
                issues.extend(self._fallback_issue(item) for item in errors[len(issues) :])
                break

            call_timeout = min(self.per_call_timeout, remaining_budget)
            issues.append(self._analyze_single_error(error, timeout=call_timeout))

        return {
            "issues": issues,
            "summary": self._build_summary(issues),
            "priority_order": self._build_priority_order(issues),
        }

    def _analyze_single_error(
        self, error: Dict[str, Any], timeout: float
    ) -> Dict[str, Any]:
        message = str(error.get("message") or "unknown")[:500]
        count = int(error.get("count") or 1)
        level = str(error.get("level") or "ERROR")
        service = str(error.get("service") or "unknown")
        pod = str(error.get("pod") or "unknown")

        system_prompt = (
            "Ты — опытный SRE-инженер в Kubernetes. "
            "Анализируй только указанную ошибку. Не выдумывай факты. "
            "root_cause — объяснение причины и шаги исправления, не пересказ текста ошибки. "
            "commands — только реальные kubectl/curl команды с pod и namespace из входных данных. "
            "Ответ — только валидный JSON по схеме."
        )
        user_prompt = (
            f"Ошибка: {message}\n"
            f"Повторений: {count}\n"
            f"Уровень: {level}\n"
            f"Сервис: {service}\n"
            f"Pod: {pod}\n\n"
            "Верни JSON с полями error, root_cause, risk, commands.\n"
            f"error должен быть точно: {message!r}\n"
            "root_cause: 1-2 предложения — вероятная причина и что проверить/исправить.\n"
            "risk: low, medium или high (OOMKilled, CrashLoopBackOff, timeout — обычно high).\n"
            f"commands: 2-3 команды для диагностики, используй pod={pod} и сервис {service}.\n"
            "Не используй плейсхолдеры (<pod>, example, param1). Без markdown."
        )

        last_error = "unknown"
        for attempt in range(self.max_retries + 1):
            raw_response, call_error = self._call_ollama(
                system_prompt,
                user_prompt,
                SINGLE_ISSUE_SCHEMA,
                timeout=timeout,
            )
            if call_error:
                last_error = call_error
                logger.warning(
                    "LLM call failed for %r (attempt %s/%s): %s",
                    message[:80],
                    attempt + 1,
                    self.max_retries + 1,
                    call_error,
                )
                continue

            parsed = self._parse_json_response(raw_response)
            if "raw_response_snippet" in parsed:
                last_error = parsed["error"]
                logger.warning(
                    "JSON parse failed for %r (attempt %s/%s): %s",
                    message[:80],
                    attempt + 1,
                    self.max_retries + 1,
                    last_error,
                )
                continue

            normalized = self._normalize_single_issue(
                parsed,
                expected_error=message,
                error_context=error,
            )
            try:
                validated = IssueItem.model_validate(normalized)
                issue = validated.model_dump()
                quality_error = self._quality_issue(issue, message)
                if quality_error:
                    last_error = quality_error
                    logger.warning(
                        "Low-quality LLM response for %r (attempt %s/%s): %s",
                        message[:80],
                        attempt + 1,
                        self.max_retries + 1,
                        quality_error,
                    )
                    continue
                return issue
            except ValidationError as exc:
                last_error = str(exc)
                logger.warning(
                    "Validation failed for %r (attempt %s/%s): %s",
                    message[:80],
                    attempt + 1,
                    self.max_retries + 1,
                    last_error,
                )

        logger.error("All LLM attempts failed for %r, using fallback", message[:80])
        fallback = self._fallback_issue(error)
        fallback["root_cause"] = (
            f"{fallback['root_cause']} (LLM: {last_error})"
        )
        return fallback

    def _quality_issue(self, issue: Dict[str, Any], expected_error: str) -> str | None:
        root_cause = issue.get("root_cause", "").strip()
        error_text = issue.get("error", "").strip()
        commands = issue.get("commands") or []

        if len(root_cause) < 20:
            return "root_cause слишком короткий"

        normalized_error = expected_error.lower()
        normalized_root = root_cause.lower()
        if normalized_root == normalized_error or normalized_root in normalized_error:
            return "root_cause повторяет текст ошибки"
        if normalized_error in normalized_root and len(root_cause) <= len(expected_error) + 10:
            return "root_cause не содержит анализа"

        if len(commands) < 2:
            return "недостаточно команд"

        lowered_commands = [command.lower() for command in commands]
        if len(set(lowered_commands)) != len(lowered_commands):
            return "дублирующиеся команды"

        for command in lowered_commands:
            if any(marker in command for marker in PLACEHOLDER_MARKERS):
                return "команды содержат плейсхолдеры"

        if not any(
            token in " ".join(lowered_commands)
            for token in ("kubectl", "curl", "journalctl", "docker", "nslookup", "dig")
        ):
            return "команды не похожи на диагностические"

        return None

    def _infer_risk(self, message: str, level: str, model_risk: str) -> str:
        text = message.lower()
        level_upper = level.upper()

        if any(token in text for token in ("oomkilled", "crashloopbackoff", "disk space low")):
            return "high"
        if any(token in text for token in ("timeout", "connection refused", "connectionrefused")):
            return "high" if level_upper == "CRITICAL" else "medium"
        if level_upper == "CRITICAL" and model_risk == "low":
            return "high"
        if level_upper == "ERROR" and model_risk == "low":
            return "medium"
        return model_risk

    def _call_ollama(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Dict[str, Any],
        timeout: float,
    ) -> tuple[str, str | None]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": schema,
            "options": {
                "temperature": 0,
                "top_k": 20,
                "top_p": 0.8,
                "num_ctx": 2048,
                "num_predict": 384,
            },
        }

        http_timeout = httpx.Timeout(
            connect=10.0,
            read=timeout,
            write=10.0,
            pool=10.0,
        )

        try:
            with httpx.Client(timeout=http_timeout) as client:
                response = client.post(f"{self.host}/api/chat", json=payload)

                if response.status_code == 400 and "format" in response.text.lower():
                    payload["format"] = "json"
                    response = client.post(f"{self.host}/api/chat", json=payload)

                if response.status_code == 404:
                    return "", (
                        f"Endpoint not found at {self.host}/api/chat. "
                        "Is Ollama running with correct model?"
                    )
                if response.status_code == 400:
                    return "", f"Bad request to LLM: {response.text}"
                if response.status_code != 200:
                    return "", (
                        f"LLM request failed with status "
                        f"{response.status_code}: {response.text}"
                    )

                result = response.json()
                raw_response = result.get("message", {}).get("content", "")
                if not raw_response:
                    return "", "LLM returned empty response"
                return raw_response, None

        except httpx.TimeoutException:
            return "", f"LLM timeout after {int(timeout)}s"
        except httpx.RequestError as exc:
            return "", f"LLM request error: {exc}"
        except Exception as exc:
            return "", f"Unexpected error: {exc}"

    def _normalize_single_issue(
        self,
        data: Dict[str, Any],
        expected_error: str,
        error_context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        item = data
        if "issues" in data and isinstance(data["issues"], list) and data["issues"]:
            item = data["issues"][0]

        risk = str(item.get("risk") or "medium").lower().strip()
        if risk not in {"low", "medium", "high"}:
            risk = "medium"

        commands = item.get("commands") or []
        if isinstance(commands, str):
            commands = [commands]
        if not isinstance(commands, list):
            commands = []
        commands = [str(command) for command in commands if command][:3]
        pod = str((error_context or {}).get("pod") or "unknown")
        service = str((error_context or {}).get("service") or "unknown")
        commands = [
            command.replace("<pod>", pod).replace("<namespace>", service)
            for command in commands
        ]

        error_text = str(item.get("error") or expected_error)
        if error_text.strip().lower() in {"", "unknown", "..."}:
            error_text = expected_error

        risk = self._infer_risk(
            expected_error,
            str((error_context or {}).get("level") or "ERROR"),
            risk,
        )

        return {
            "error": error_text,
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

    def _fallback_issue(self, error: Dict[str, Any]) -> Dict[str, Any]:
        message = str(error.get("message") or "unknown")
        level = str(error.get("level") or "ERROR").upper()
        service = str(error.get("service") or "unknown")
        pod = str(error.get("pod") or "<pod>")
        risk = self._infer_risk(message, level, "medium")

        root_cause = (
            f"Сервис {service} в pod {pod} сообщает: {message}. "
            f"Проверьте логи, события и ресурсы контейнера."
        )
        if "oomkilled" in message.lower():
            root_cause = (
                f"Контейнер в pod {pod} превысил лимит памяти. "
                "Проверьте requests/limits и утечки памяти в приложении."
            )
        elif "crashloopbackoff" in message.lower():
            root_cause = (
                f"Pod {pod} перезапускается из-за падения процесса. "
                "Проверьте логи предыдущего контейнера и readiness/liveness probes."
            )
        elif "timeout" in message.lower():
            root_cause = (
                f"Сервис {service} не отвечает вовремя. "
                "Проверьте сетевую связность, нагрузку и зависимости upstream."
            )

        return {
            "error": message,
            "root_cause": root_cause,
            "risk": risk,
            "commands": [
                f"kubectl logs {pod} --tail=100",
                f"kubectl describe pod {pod}",
                f"kubectl get pods -l app={service}",
            ],
        }

    def _build_summary(self, issues: List[Dict[str, Any]]) -> str:
        if not issues:
            return "Не удалось сформировать итог по логам."

        high_risk = [issue for issue in issues if issue.get("risk") == "high"]
        parts = [f"Обнаружено {len(issues)} уникальных ошибок."]
        if high_risk:
            names = ", ".join(issue["error"][:60] for issue in high_risk[:3])
            parts.append(f"Критичных: {len(high_risk)} ({names}).")
        return " ".join(parts)

    def _build_priority_order(self, issues: List[Dict[str, Any]]) -> List[str]:
        sorted_issues = sorted(
            issues,
            key=lambda issue: (
                RISK_ORDER.get(str(issue.get("risk", "medium")).lower(), 1),
                issue.get("error", ""),
            ),
        )
        return [issue["error"] for issue in sorted_issues]

    def _normalize_remediation(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Гарантирует наличие всех обязательных полей в ответе LLM."""
        issues_raw = data.get("issues")
        if not isinstance(issues_raw, list):
            if any(key in data for key in ("error", "root_cause", "commands")):
                issues_raw = [data]
            else:
                issues_raw = []

        issues: List[Dict[str, Any]] = []
        for item in issues_raw:
            if not isinstance(item, dict):
                continue
            issues.append(self._normalize_single_issue(item, expected_error="unknown"))

        summary = data.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            summary = self._build_summary(issues)

        issue_errors = [issue["error"] for issue in issues]
        priority = data.get("priority_order")
        placeholder_hints = ("ошибка с высшим приоритетом", "...", "текст ошибки")
        if not isinstance(priority, list) or not priority:
            priority = issue_errors
        else:
            priority = [str(item) for item in priority if item]
            if any(any(hint in item.lower() for hint in placeholder_hints) for item in priority):
                priority = issue_errors
            elif issue_errors and not any(
                any(err in item or item in err for err in issue_errors) for item in priority
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
        for index, char in enumerate(raw_response[start_pos:], start=start_pos):
            if char == "{":
                bracket_count += 1
            elif char == "}":
                bracket_count -= 1
                if bracket_count == 0:
                    end_pos = index
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

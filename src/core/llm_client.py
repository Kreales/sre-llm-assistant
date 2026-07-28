import httpx
import json
import re
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self, host: str = "http://ollama:11434", model: str = "gemma:2b"):
        self.host = host.rstrip("/")
        self.model = model

    def generate_remediation(self, logs_text: str) -> Dict[str, Any]:
        """
        Запрашивает у LLM анализ логов и рекомендации.
        Возвращает словарь или {"error": "..."}
        """
        # Упрощённый промпт для быстрой генерации
        system_prompt = (
            "Ты — опытный SRE-инженер. Твоя задача — проанализировать реальные логи и дать точные, actionable рекомендации. "
            "Не выдумывай, не повторяй шаблоны. Не используй фразы вроде 'краткое описание причины' или 'Вариант команды для исправления'. "
            "Если логи не содержат достаточно информации — верни {'error': 'Insufficient log context'}."
        )

        user_prompt = (
            f"Вот 30 последних ошибок из production:\n{logs_text}\n\n"
            "Ответь на русском языке в формате JSON с полями:\n"
            "- root_cause: конкретная причина (не общая)\n"
            "- commands: список из 2–3 реальных CLI-команд (например: kubectl describe pod ..., journalctl -u postgres)\n"
            "- risk: low/medium/high\n"
            "- explanation: 1–2 предложения, почему это произошло и как предотвратить\n"
            "ВАЖНО: НЕ ВКЛЮЧАЙ в ответ никакие другие поля и пояснения. Только чистый JSON."
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_k": 40,
                "top_p": 0.9
            }
        }

        try:
            # Увеличенный таймаут для 2 vCPU
            with httpx.Client(timeout=300.0) as client:
                response = client.post(f"{self.host}/api/chat", json=payload)
                
                # Проверяем статус ответа
                if response.status_code == 404:
                    return {"error": f"Endpoint not found at {self.host}/api/chat. Is Ollama running with correct model?"}
                elif response.status_code == 400:
                    error_detail = response.text
                    return {"error": f"Bad request to LLM: {error_detail}"}
                elif response.status_code != 200:
                    return {"error": f"LLM request failed with status {response.status_code}: {response.text}"}
                
                result = response.json()

                # Извлекаем текст ответа
                raw_response = result.get("message", {}).get("content", "")
                
                if not raw_response:
                    return {"error": "LLM returned empty response", "raw": result}

                            # Ищем JSON в ответе
            start_pos = raw_response.find('{')
            if start_pos == -1:
                return {"error": "No JSON object found in LLM response", "raw_response_snippet": raw_response[:200]}
            
            bracket_count = 0
            end_pos = -1
            for i, char in enumerate(raw_response[start_pos:], start=start_pos):
                if char == '{':
                    bracket_count += 1
                elif char == '}':
                    bracket_count -= 1
                    if bracket_count == 0:
                        end_pos = i
                        break
            
            if end_pos != -1:
                json_str = raw_response[start_pos:end_pos+1]
            else:
                # Если скобки не закрылись, пробуем regex как fallback
                json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                else:
                    return {
                        "error": "LLM did not return valid JSON format",
                        "raw_response_snippet": raw_response[:200] + "..."
                    }

            # Попробуем распарсить
            try:
                parsed_json = json.loads(json_str)
                return parsed_json
            except json.JSONDecodeError:
                # Если не получилось, пробуем заменить одинарные кавычки
                try:
                    fixed_str = json_str.replace("'", '"')
                    return json.loads(fixed_str)
                except json.JSONDecodeError:
                    return {
                        "error": "Could not parse JSON from LLM response",
                        "raw_response_snippet": raw_response[:200] + "..."
                    }
                        

        except httpx.TimeoutException:
            logger.error(f"LLM request timed out after 120s to {self.host}")
            return {"error": "LLM timeout after 120s"}
        except httpx.RequestError as e:
            logger.error(f"LLM request error: {e}")
            return {"error": f"LLM request error: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected error during LLM request: {e}")
            return {"error": f"Unexpected error: {str(e)}"}


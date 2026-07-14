import httpx
import json
import re
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self, host: str = "http://ollama:11434", model: str = "tinyllama"):
        self.host = host.rstrip("/")
        self.model = model

    def generate_remediation(self, logs_text: str) -> Dict[str, Any]:
        """
        Запрашивает у LLM анализ логов и рекомендации.
        Возвращает словарь или {"error": "..."}
        """
        # Упрощённый промпт для быстрой генерации
        system_prompt = "Ты — SRE-инженер. Отвечай ТОЛЬКО валидным JSON без пояснений."

        user_prompt = f"""
        Проанализируй логи и верни JSON:
        {{
          "root_cause": "краткое описание причины",
          "commands": ["команда 1", "команда 2"],
          "risk": "low|medium|high",
          "explanation": "объяснение на русском"
        }}

        Логи:
        {logs_text[:1000]}  # ограничиваем длину для быстроты
        """

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 256,  # ограничиваем длину генерации
                "top_k": 20,
                "top_p": 0.9
            }
        }

        try:
            # Увеличенный таймаут для 2 vCPU
            with httpx.Client(timeout=120.0) as client:
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

                # Ищем JSON в ответе (LLM может обернуть в ```json или просто вернуть объект)
                json_match = re.search(r'\{(?:[^{}]|(?R))*\}', raw_response, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
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
                else:
                    return {
                        "error": "LLM did not return valid JSON format",
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

# Тестирование (опционально)
if __name__ == "__main__":
    client = LLMClient()
    sample_logs = "[2024-05-15T10:00:00Z] ERROR auth-service: ConnectionRefusedError: postgres:5432 refused"
    result = client.generate_remediation(sample_logs)
    print(json.dumps(result, indent=2, ensure_ascii=False))

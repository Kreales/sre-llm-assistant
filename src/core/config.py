# Настройки приложения из переменных окружения и .env.
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Центральная конфигурация API, OpenSearch и Ollama."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # неизвестные переменные из .env не ломают старт
        case_sensitive=False,
    )

    es_host: str = "http://opensearch:9200"
    es_index_pattern: str = "sre-logs-*"
    ollama_host: str = "http://ollama:11434"
    ollama_model: str = "llama3.2:3b"
    log_level: str = "info"
    api_port: int = 8000
    analyze_max_unique_errors: int = 5  # сколько уникальных ошибок отдаём в LLM
    llm_timeout_seconds: float = 300.0  # общий бюджет времени на весь анализ
    llm_per_call_timeout_seconds: float = 90.0  # таймаут одного запроса к Ollama
    llm_max_retries: int = 2


settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    es_host: str = "http://opensearch:9200"
    es_index_pattern: str = "sre-logs-*"
    ollama_host: str = "http://ollama:11434"
    ollama_model: str = "gemma:2b"
    log_level: str = "info"
    api_port: int = 8000
    analyze_max_unique_errors: int = 5
    llm_timeout_seconds: float = 300.0


settings = Settings()

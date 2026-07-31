import os
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    es_host: str = "http://opensearch:9200"
    ollama_host: str = "http://ollama:11434"
    ollama_model: str = "gemma:2b"
    log_level: str = "info"
    api_port: int = 8000

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()


def get_es_host(override: Optional[str] = None) -> str:
    return override or os.getenv("ES_HOST", settings.es_host)


def get_ollama_host(override: Optional[str] = None) -> str:
    return override or os.getenv("OLLAMA_HOST", settings.ollama_host)


def get_ollama_model(override: Optional[str] = None) -> str:
    return override or os.getenv("OLLAMA_MODEL", settings.ollama_model)

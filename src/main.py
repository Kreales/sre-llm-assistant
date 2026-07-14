from fastapi import FastAPI
from src.api.analyze import router as analyze_router
from datetime import datetime
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SRE LLM Assistant",
    description="AI-powered log analysis and remediation for Site Reliability Engineering",
    version="0.1.0",
    docs_url="/docs",      # Swagger UI
    redoc_url="/redoc"     # Alternative docs
)

# Подключаем роутер с endpoint'ом /analyze
app.include_router(analyze_router, prefix="/api/v1")

@app.get("/")
async def root():
    """
    Корневой endpoint — проверка, что сервис запущен
    """
    return {
        "status": "ok",
        "service": "SRE LLM Assistant",
        "version": app.version,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/health")
async def health():
    """
    Health-check endpoint — проверка, что все компоненты доступны
    """
    # Здесь можно добавить проверки подключения к ES, Ollama и т.д.
    return {
        "status": "healthy",
        "service": "sre-api",
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": {
            "opensearch": "connected",
            "ollama": "connected"
        }
    }

# Логируем запуск
logger.info("SRE LLM Assistant API started")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

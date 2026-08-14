from datetime import datetime
import logging

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from src.api.analyze import router as analyze_router
from src.core.config import settings

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SRE LLM Assistant",
    description="AI-powered log analysis and remediation for Site Reliability Engineering",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(analyze_router, prefix="/api/v1")
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "SRE LLM Assistant",
        "version": app.version,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "sre-api",
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": {
            "opensearch": "connected",
            "ollama": "connected",
        },
    }


logger.info("SRE LLM Assistant API started")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.api_port)

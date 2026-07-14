# src/api/analyze.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from src.core.llm_client import LLMClient
from src.core.es_client import OpenSearchClient
from datetime import datetime

router = APIRouter()
llm = LLMClient()
es = OpenSearchClient()

class AnalyzeRequest(BaseModel):
    hours: float = 1.0
    severity: str = "ERROR"

    class Config:
        # Для совместимости с JSON из curl
        extra = "forbid"
        arbitrary_types_allowed = False

@router.post("/analyze")
async def analyze_incident(req: AnalyzeRequest):
    minutes = int(req.hours * 60)
    logs = es.get_error_logs(minutes=minutes, limit=30)

    if not logs:
        return {
            "status": "no_logs",
            "message": f"No error logs found in the last {req.hours} hours",
            "request": req.dict()
        }

    # Формируем текст для LLM
    log_text = "\n".join([
        f"[{log.get('@timestamp', '')}] {log.get('level', 'INFO')} [{log.get('service', 'unknown')}]: {log.get('message', '')}"
        for log in logs
    ])

    result = llm.generate_remediation(log_text)

    return {
        "request": req.dict(),
        "logs_analyzed": len(logs),
        "remediation": result,
        "timestamp": datetime.utcnow().isoformat()
    }

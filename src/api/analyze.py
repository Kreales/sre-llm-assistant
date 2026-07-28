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
    groups = es.get_error_groups(minutes=minutes, top_k=3)

    if not groups:
        return {"status": "no_logs", ...}

    analysis_results = []
    for group in groups:
        # Собери текст для LLM: группа + примеры
        group_text = f"Ошибка ({group['count']} раз):\n{group['message']}\nПримеры:\n"
        for log in group["samples"]:
            group_text += f"- [{log['@timestamp']}] {log['service']}: {log['message']}\n"

        result = llm.generate_remediation(group_text)
        analysis_results.append({
            "error_pattern": group["message"],
            "count": group["count"],
            "remediation": result
        })

    return {
        "request": req.dict(),
        "error_groups_analyzed": len(groups),
        "groups": analysis_results,
        "timestamp": datetime.utcnow().isoformat()
    }

    print(f"🔍 Sending {len(logs)} logs to LLM:\n{log_text[:500]}...")

    result = llm.generate_remediation(log_text)

    return {
        "request": req.dict(),
        "logs_analyzed": len(logs),
        "remediation": result,
        "timestamp": datetime.utcnow().isoformat()
    }

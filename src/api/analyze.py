# src/api/analyze.py
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from src.core.llm_client import LLMClient
from src.core.es_client import OpenSearchClient
from datetime import datetime, timezone

router = APIRouter()
llm = LLMClient()
es = OpenSearchClient()


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hours: float = 1.0
    severity: str = "ERROR"
    limit: int = 30


@router.post("/analyze")
async def analyze_incident(req: AnalyzeRequest):
    minutes = int(req.hours * 60)
    logs = es.get_error_logs(minutes=minutes, limit=req.limit)

    if not logs:
        return {
            "status": "no_logs",
            "message": f"No error logs found in the last {req.hours} hours",
            "request": req.model_dump(),
        }

    # Все найденные логи уходят в LLM, а не только первый
    log_text = "\n".join(
        [
            f"[{log.get('@timestamp', '')}] {log.get('level', 'INFO')} "
            f"[{log.get('service', 'unknown')}]: {log.get('message', '')}"
            for log in logs
        ]
    )

    print(f"🔍 Sending {len(logs)} logs to LLM:\n{log_text[:500]}...")

    result = llm.generate_remediation(log_text)

    return {
        "request": req.model_dump(),
        "logs_analyzed": len(logs),
        "remediation": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

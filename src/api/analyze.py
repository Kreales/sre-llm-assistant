from collections import Counter
from datetime import datetime, timezone
import logging

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from src.core.config import settings
from src.core.es_client import OpenSearchClient
from src.core.llm_client import LLMClient

logger = logging.getLogger(__name__)

router = APIRouter()
llm = LLMClient()
es = OpenSearchClient()


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hours: float = 1.0
    severity: str = "ERROR"
    limit: int = Field(default=10, ge=1, le=50)


def _build_error_list(logs: list) -> tuple[list[dict], list[dict]]:
    """
    Топ уникальных ошибок со счётчиками и метаданными для LLM.
    Каждая ошибка анализируется отдельным запросом — стабильнее для маленькой модели.
    """
    counts = Counter(log.get("message", "unknown") for log in logs)
    by_message: dict[str, list] = {}
    for log in logs:
        by_message.setdefault(log.get("message", "unknown"), []).append(log)

    top_errors = counts.most_common(settings.analyze_max_unique_errors)
    errors_for_llm = []
    summary = []

    for idx, (message, count) in enumerate(top_errors, start=1):
        sample = by_message[message][0]
        errors_for_llm.append(
            {
                "message": message,
                "count": count,
                "level": sample.get("level", "ERROR"),
                "service": sample.get("service", "unknown"),
                "pod": sample.get("pod", "unknown"),
            }
        )
        summary.append(
            {
                "rank": idx,
                "message": message,
                "count": count,
                "services": sorted(
                    {s.get("service", "unknown") for s in by_message[message]}
                ),
            }
        )

    return errors_for_llm, summary


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

    errors_for_llm, error_summary = _build_error_list(logs)

    logger.info(
        "Sending %s logs (%s unique errors) to LLM",
        len(logs),
        len(error_summary),
    )

    result = llm.generate_remediation(errors_for_llm)

    return {
        "request": req.model_dump(),
        "logs_analyzed": len(logs),
        "unique_errors": len(error_summary),
        "error_summary": error_summary,
        "remediation": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

# src/api/analyze.py
from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from src.core.es_client import OpenSearchClient
from src.core.llm_client import LLMClient

router = APIRouter()
llm = LLMClient()
es = OpenSearchClient()


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hours: float = 1.0
    severity: str = "ERROR"
    limit: int = 30


def _build_logs_prompt(logs: list) -> tuple[str, list[dict]]:
    """
    Собирает текст для LLM из ВСЕХ логов: группировка по message + счётчики.
    Так модель видит полный набор ошибок, а не цепляется за первую строку.
    """
    counts = Counter(log.get("message", "unknown") for log in logs)
    by_message: dict[str, list] = {}
    for log in logs:
        by_message.setdefault(log.get("message", "unknown"), []).append(log)

    summary = []
    blocks = [
        f"Всего логов: {len(logs)}",
        f"Уникальных ошибок: {len(counts)}",
        "",
        "Разбери КАЖДУЮ ошибку ниже (не только первую):",
        "",
    ]

    for idx, (message, count) in enumerate(counts.most_common(), start=1):
        samples = by_message[message][:3]
        sample_lines = [
            f"    • [{s.get('@timestamp', '')}] "
            f"{s.get('level', '?')} / {s.get('service', '?')} / {s.get('pod', '?')}"
            for s in samples
        ]
        blocks.append(f"{idx}. [{count}x] {message}")
        blocks.extend(sample_lines)
        blocks.append("")
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

    return "\n".join(blocks), summary


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

    log_text, error_summary = _build_logs_prompt(logs)

    print(
        f"🔍 Sending {len(logs)} logs "
        f"({len(error_summary)} unique errors, {len(log_text)} chars) to LLM"
    )
    print(log_text[:800] + ("..." if len(log_text) > 800 else ""))

    result = llm.generate_remediation(log_text)

    return {
        "request": req.model_dump(),
        "logs_analyzed": len(logs),
        "unique_errors": len(error_summary),
        "error_summary": error_summary,
        "remediation": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

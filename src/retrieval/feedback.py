"""Analyst feedback logging for retrieval quality and citation corrections.

Feedback is intentionally append-only JSONL under data/logs so it is observable,
easy to inspect, and separate from deterministic retrieval/query logs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.config import settings


def feedback_log_path(base=None) -> Path:
    root = Path(base) if base else settings.data_path
    return root / "logs" / "feedback.jsonl"


def build_feedback_record(
    *,
    question: str,
    rating: str,
    citations_correct: bool,
    comment: str = "",
    citation_correction: str = "",
    trace: dict | None = None,
) -> dict:
    trace = trace or {}
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "rating": rating,
        "citations_correct": citations_correct,
        "comment": comment,
        "citation_correction": citation_correction,
        "retrieved_ids": trace.get("evidence_ids", []),
        "evidence_used": trace.get("evidence_used", []),
        "prompt_version": trace.get("prompt_version", ""),
        "guardrail": trace.get("guardrail") or trace.get("scope_guardrail") or {},
    }


def write_feedback(record: dict, *, base=None) -> Path:
    path = feedback_log_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


"""Stage 17 — per-query logging (observability).

Build and persist a structured record of every query: the parsed intent/metadata, the ids at each
retrieval stage (bm25 / vector / rrf / reranked / evidence), the prompt version, the guardrail
decision, latency, token usage, and cost. Appended as JSON lines to ``data/logs/queries.jsonl``.

Unlike the deterministic pipeline artifacts, query logs are operational: they carry latency and
cost (wall-clock is fine here — these are not reproducible artifacts).
"""

from __future__ import annotations

import json
from pathlib import Path

from src.config import settings

# Claude Opus 4.8 pricing (USD per 1M tokens) — see ADR-005.
_INPUT_PER_1M = 5.0
_OUTPUT_PER_1M = 25.0


def cost_usd(usage: dict) -> float:
    it = usage.get("input_tokens", 0) or 0
    ot = usage.get("output_tokens", 0) or 0
    return round(it / 1_000_000 * _INPUT_PER_1M + ot / 1_000_000 * _OUTPUT_PER_1M, 6)


def build_log_record(result, *, latency_s: float, usage: dict | None = None) -> dict:
    """Assemble the query-log record from a PipelineResult (no I/O)."""
    usage = usage or (result.answer.usage if result.answer else {}) or {}
    t = result.trace
    return {
        "query": t.get("query"),
        "intents": t.get("intents"),
        "companies": t.get("companies"),
        "years": t.get("years"),
        "filter": t.get("filter"),
        "plan": t.get("plan"),
        "bm25_ids": t.get("bm25_ids"),
        "vector_ids": t.get("vector_ids"),
        "rrf_ids": t.get("rrf_ids"),
        "reranked_ids": t.get("reranked_ids"),
        "evidence_ids": t.get("evidence_ids"),
        "evidence_used": t.get("evidence_used"),
        "prompt_version": t.get("prompt_version"),
        "guardrail": t.get("guardrail"),
        "refused": result.refused,
        "confidence": result.guardrail.confidence if result.guardrail else "",
        "latency_s": round(latency_s, 4),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cost_usd": cost_usd(usage),
    }


def log_path(base=None) -> Path:
    root = Path(base) if base is not None else settings.data_path
    return root / "logs" / "queries.jsonl"


def write_log(record: dict, *, base=None) -> Path:
    """Append one query record as a JSON line to data/logs/queries.jsonl."""
    p = log_path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return p

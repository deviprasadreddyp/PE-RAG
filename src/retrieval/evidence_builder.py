"""Stages 10-11 — context builder + evidence grounding (deterministic; no LLM).

Turn the final ranked chunks into a numbered **evidence package**: each chunk gets a stable
``[E#]`` id and a human tag (``[AAPL 10-K FY2024 · Risk Factors]``). The prompt and the model's
citations reference ``E1/E2/...`` rather than raw filenames, so every claim is traceable to a
specific retrieved chunk. Order is best-first (as ranked). Capped at ``rerank_top_k``.
"""

from __future__ import annotations

from src.config import settings
from src.schemas import Chunk, Evidence, RetrievalResult

SEP = "\n---\n"


def _period(chunk: Chunk) -> str:
    if chunk.year:
        return f"FY{chunk.year}"
    return chunk.fiscal_period or ""


def evidence_tag(chunk: Chunk) -> str:
    """Human citation tag, e.g. '[AAPL 10-K FY2024 · Risk Factors]'."""
    head = " ".join(p for p in (chunk.ticker or chunk.company, chunk.form, _period(chunk)) if p)
    return f"[{head} · {chunk.section}]" if chunk.section else f"[{head}]"


def build_evidence(results: list[RetrievalResult], *, limit: int | None = None) -> list[Evidence]:
    """Ranked results -> numbered Evidence ([E1..], tagged), capped at ``limit``/rerank_top_k."""
    limit = limit or settings.rerank_top_k
    return [
        Evidence(evidence_id=f"E{i}", chunk=r.chunk, score=r.score, tag=evidence_tag(r.chunk))
        for i, r in enumerate(results[:limit], start=1)
    ]


def render_context(evidence: list[Evidence]) -> str:
    """Render the evidence package into the ``<context>`` block for the prompt."""
    blocks = [f"{e.evidence_id}: {e.tag} (chunk {e.chunk.id})\n{e.chunk.text}" for e in evidence]
    return SEP.join(blocks)

"""Stage 15 — response parsing (deterministic; no LLM).

Assemble the final ``Answer`` from the structured ``AnswerBody`` (Stage 14): render the sections
to markdown, attach resolved ``Citation`` s (Stage 16) and the retrieved results, and carry usage.
Also builds the standard refusal ``Answer`` used when guardrails reject before the LLM call.
"""

from __future__ import annotations

from src.retrieval.citation_mapper import map_citations
from src.schemas import Answer, AnswerBody, Evidence, RetrievalResult

REFUSAL = "Information unavailable in the provided filings."


def render_markdown(body: AnswerBody) -> str:
    """Render the structured answer sections to markdown (omit empty sections)."""
    parts: list[str] = []
    if body.executive_summary:
        parts.append(f"## Executive Summary\n{body.executive_summary}")
    if body.comparison:
        parts.append(f"## Comparison\n{body.comparison}")
    if body.supporting_evidence:
        parts.append(f"## Supporting Evidence\n{body.supporting_evidence}")
    if body.limitations:
        parts.append(f"## Limitations\n{body.limitations}")
    if body.confidence:
        parts.append(f"**Confidence:** {body.confidence}")
    return "\n\n".join(parts)


def build_answer(body: AnswerBody, evidence: list[Evidence], *,
                 retrieved: list[RetrievalResult] | None = None, usage: dict | None = None) -> Answer:
    """AnswerBody + evidence -> final Answer with resolved citations."""
    return Answer(
        answer=render_markdown(body),
        sources=map_citations(body, evidence),
        retrieved=retrieved or [],
        usage=usage or {},
    )


def refusal_answer(reason: str = "", *, usage: dict | None = None) -> Answer:
    """The standard cite-or-refuse response when guardrails reject (no LLM call was made)."""
    text = REFUSAL if not reason else f"{REFUSAL}\n\n{reason}"
    return Answer(answer=text, sources=[], retrieved=[], usage=usage or {})

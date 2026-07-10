"""Relevance judgment for evaluation (deterministic; no LLM).

Ground truth for this closed corpus is expressed as EITHER exact ``expected_chunk_ids`` (if
hand-annotated) OR metadata expectations (``companies`` / ``years`` / ``forms`` / ``sections``) —
so we never need to hand-label all ~32K chunks. A retrieved chunk is relevant if it matches.

Helpers here produce the per-result relevance flags and entity-level recall proxies used by the
retrieval metrics (``src/eval/metrics.py``).
"""

from __future__ import annotations

from collections.abc import Sequence

from src.retrieval import facets as facet_mod
from src.schemas import Chunk


def is_relevant(chunk: Chunk, expected: dict) -> bool:
    """True if ``chunk`` satisfies the case's ground truth (exact chunk ids OR metadata)."""
    ids = expected.get("expected_chunk_ids")
    if ids:
        return chunk.id in set(ids)
    if expected.get("companies") and chunk.ticker not in expected["companies"]:
        return False
    if expected.get("years") and chunk.year not in expected["years"]:
        return False
    if expected.get("forms") and chunk.form not in expected["forms"]:
        return False
    if expected.get("sections"):
        facets = expected.get("facets") or facet_mod.extract_facets(
            expected.get("question", ""),
            sections=expected.get("sections") or (),
        )
        if not any(facet_mod.chunk_matches_section(chunk, section, facets=facets)
                   for section in expected["sections"]):
            return False
    return True


def relevance_flags(chunks: Sequence[Chunk], expected: dict) -> list[int]:
    """Binary relevance (1/0) for a ranked list of chunks, in order."""
    return [1 if is_relevant(c, expected) else 0 for c in chunks]


def company_recall(chunks: Sequence[Chunk], expected: dict) -> float:
    """Fraction of the case's expected companies that appear in the retrieved chunks."""
    want = set(expected.get("companies") or [])
    if not want:
        return 0.0
    got = {c.ticker for c in chunks}
    return len(want & got) / len(want)


def pooled_recall_at_k(flags: Sequence[int], pool_relevant: int, k: int) -> float:
    """Recall@k against a POOLED relevant count (union of relevant found across strategies).

    Classic recall needs the total number of relevant items, which we don't have without full
    labels. In the A/B harness we pool the relevant chunks found by any strategy and use that as the
    denominator — a standard IR trick — so strategies are comparable.
    """
    if pool_relevant <= 0:
        return 0.0
    return sum(1 for f in flags[:k] if f) / pool_relevant

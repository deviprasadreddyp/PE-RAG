"""Stage 7 — Reciprocal Rank Fusion (deterministic; no LLM; ours, not LangChain).

Fuse the BM25 and vector ranked lists using **ranks only**, so no score normalization is
needed across the incomparable BM25 and cosine scales:

    score(d) = Σ_r  1 / (k + rank_r(d))          k = 60 (default), rank 1-based

A document absent from a list contributes 0 from that list. When the same chunk appears in both
lists, we keep the representation that carries text (the vector one) so downstream stages have it.
Output is ordered by fused score (descending), ties broken by first-seen order (deterministic).
"""

from __future__ import annotations

from src.config import settings
from src.schemas import RetrievalResult


def reciprocal_rank_fusion(
    *ranked_lists: list[RetrievalResult], k: int | None = None, top_n: int | None = None
) -> list[RetrievalResult]:
    """RRF-fuse ranked lists into one ranked list (score = fused RRF score)."""
    k = k or settings.rrf_k
    scores: dict[str, float] = {}
    best: dict[str, RetrievalResult] = {}
    for results in ranked_lists:
        for rank, r in enumerate(results, start=1):
            cid = r.chunk.id
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            prev = best.get(cid)
            if prev is None or (not prev.chunk.text and r.chunk.text):  # prefer a text-bearing copy
                best[cid] = r
    fused = [RetrievalResult(chunk=best[cid].chunk, score=score) for cid, score in scores.items()]
    fused.sort(key=lambda r: r.score, reverse=True)             # stable -> ties keep first-seen order
    return fused[:top_n] if top_n else fused

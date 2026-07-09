"""Retrieval & answer-quality metrics (pure functions; no network).

Ranking metrics take a ``relevance`` list — booleans/0-1 in ranked order (position 0 = top hit):
- ``precision_at_k`` — fraction of the top-k that are relevant.
- ``recall_at_k`` — fraction of all relevant items found in the top-k (needs ``total_relevant``).
- ``hit_at_k`` — 1.0 if any relevant item is in the top-k, else 0.0.
- ``reciprocal_rank`` / ``mrr`` — 1/rank of the first relevant hit (per query / averaged).
- ``ndcg_at_k`` — rank-quality with logarithmic discount (binary gains).

Answer metrics compare cited evidence ids to the evidence actually supplied:
- ``citation_groundedness`` — fraction of cited ids that exist in the evidence (1.0 = no
  hallucinated citations).
- ``citation_coverage`` — fraction of supplied evidence the answer actually cited.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def precision_at_k(relevance: Sequence[int], k: int) -> float:
    if k <= 0:
        return 0.0
    top = relevance[:k]
    return sum(1 for r in top if r) / k


def recall_at_k(relevance: Sequence[int], total_relevant: int, k: int) -> float:
    if total_relevant <= 0:
        return 0.0
    return sum(1 for r in relevance[:k] if r) / total_relevant


def hit_at_k(relevance: Sequence[int], k: int) -> float:
    return 1.0 if any(relevance[:k]) else 0.0


def reciprocal_rank(relevance: Sequence[int]) -> float:
    for i, r in enumerate(relevance, start=1):
        if r:
            return 1.0 / i
    return 0.0


def mrr(relevances: Sequence[Sequence[int]]) -> float:
    rows = list(relevances)
    return sum(reciprocal_rank(r) for r in rows) / len(rows) if rows else 0.0


def dcg_at_k(relevance: Sequence[int], k: int) -> float:
    return sum((1.0 if r else 0.0) / math.log2(i + 1)
               for i, r in enumerate(relevance[:k], start=1))


def ndcg_at_k(relevance: Sequence[int], k: int) -> float:
    idcg = dcg_at_k(sorted(relevance, reverse=True), k)
    return dcg_at_k(relevance, k) / idcg if idcg else 0.0


def citation_groundedness(cited_ids: Sequence[str], evidence_ids: Sequence[str]) -> float:
    if not cited_ids:
        return 0.0
    evi = set(evidence_ids)
    return sum(1 for c in cited_ids if c in evi) / len(cited_ids)


def citation_coverage(cited_ids: Sequence[str], evidence_ids: Sequence[str]) -> float:
    if not evidence_ids:
        return 0.0
    evi = set(evidence_ids)
    used = {c for c in cited_ids if c in evi}
    return len(used) / len(evidence_ids)

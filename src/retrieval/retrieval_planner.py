"""Stage 5 — retrieval planning (deterministic; no LLM).

The query type determines the retrieval STRATEGY (see the decision tree in
architecture/RETRIEVAL_DESIGN.md §6):

- Comparison / multi-company  -> ``per_entity``: retrieve top-N PER company so one issuer
  cannot dominate the candidate pool.
- Trend / temporal            -> ``per_period``: spread candidates across the requested/
  available years for the same company.
- Otherwise                   -> ``global``: a single global top-K.

Section intent adds soft ``section_boosts`` (e.g. Risk -> "Risk Factors"; Financial -> MD&A +
Financial Statements). Boosts are applied WITHIN the hard-filtered set — they never override a
hard metadata filter.
"""

from __future__ import annotations

from math import ceil

from src.config import settings
from src.schemas import QueryAnalysis, RetrievalPlan

_FINANCIAL_SECTIONS = [
    "Management's Discussion and Analysis",
    "Financial Statements and Supplementary Data",
]


def plan_retrieval(qa: QueryAnalysis) -> RetrievalPlan:
    """QueryAnalysis -> RetrievalPlan (mode, per-entity budget, section boosts, pool size)."""
    n = len(qa.companies)
    pool = settings.candidate_pool

    if "Comparison" in qa.intents or n >= 2:
        per = max(settings.vector_top_k // max(n, 1), ceil(pool / max(n, 1)))
        mode, per_entity_k, pool_size = "per_entity", per, per * max(n, 1)
    elif "Trend" in qa.intents or "Temporal" in qa.intents:
        mode, per_entity_k, pool_size = "per_period", 0, pool
    else:
        mode, per_entity_k, pool_size = "global", 0, pool

    boosts = list(qa.section_intent)
    if not boosts:
        if "Risk" in qa.intents:
            boosts = ["Risk Factors"]
        elif "Financial" in qa.intents:
            boosts = list(_FINANCIAL_SECTIONS)

    return RetrievalPlan(
        mode=mode, per_entity_k=per_entity_k, section_boosts=boosts, pool_size=pool_size
    )

"""Stage 12 — deterministic guardrails (NO LLM).

The gate between retrieval and the single LLM call. Implements the decision table in
architecture/RETRIEVAL_DESIGN.md §8. The golden rule: **never answer outside retrieved
evidence** — when in doubt, refuse (``ok=False``), and the refusal path skips the LLM call
entirely (zero calls).

``top_similarity`` is the best cosine similarity from the vector stage (0-1), computed by the
pipeline — reranker scores are unbounded and not used for the bands. Confidence follows
PHYSICAL_SPEC §9 (High ≥0.75 · Medium ≥0.55 · Low <0.55).
"""

from __future__ import annotations

from src.config import settings
from src.schemas import Evidence, GuardrailResult, QueryAnalysis


def _confidence(sim: float) -> str:
    if sim >= 0.75:
        return "High"
    if sim >= 0.55:
        return "Medium"
    return "Low"


def evaluate(qa: QueryAnalysis, evidence: list[Evidence], *, top_similarity: float) -> GuardrailResult:
    """Run the deterministic checks in order; first failure refuses, else accept/warn."""
    # 1. no evidence at all
    if not evidence:
        return GuardrailResult(ok=False, action="reject",
                               reason="No relevant evidence was retrieved.", confidence="Low")

    # 2. minimum similarity — evidence too weak to trust
    if top_similarity < settings.min_similarity:
        return GuardrailResult(ok=False, action="reject",
                               reason="Retrieved evidence is below the similarity threshold.",
                               confidence="Low")

    covered = {e.chunk.ticker for e in evidence if e.chunk.ticker}

    # 3. company coverage — a requested company has zero evidence
    missing = [c for c in qa.companies if c not in covered]
    if missing:
        return GuardrailResult(ok=False, action="reject",
                               reason=f"No evidence found for: {', '.join(missing)}.",
                               confidence="Low")

    # 4. comparison diversity — a comparison needs >= 2 companies in the evidence
    if "Comparison" in qa.intents and len(qa.companies) != 1 and len(covered) < 2:
        return GuardrailResult(ok=False, action="reject",
                               reason="A comparison needs evidence from at least two companies.",
                               confidence="Low")

    conf = _confidence(top_similarity)

    # 5. temporal coverage — requested year missing -> warn (answer over available years)
    missing_years = [y for y in qa.years if y not in {e.chunk.year for e in evidence}]
    if missing_years:
        return GuardrailResult(ok=True, action="warn", confidence=conf,
                               reason="No evidence for year(s): "
                                      + ", ".join(str(y) for y in missing_years) + ".")

    # 6. weak-but-usable band -> warn; otherwise accept
    action = "accept" if top_similarity > 0.50 else "warn"
    return GuardrailResult(ok=True, action=action, reason="", confidence=conf)

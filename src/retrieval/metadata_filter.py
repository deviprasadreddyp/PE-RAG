"""Stage 4 — hard-filter construction (deterministic; no LLM).

Convert the extracted metadata (Stage 3) into a ``HardFilter`` — the EXACT constraints
(company / year / quarter / form) applied BEFORE ranking. These cannot be traded off: an
"AAPL 2024 10-K" question must never return TSLA. Section intent is deliberately NOT a hard
filter — it is a soft boost handled by the retrieval planner (Stage 5).

The ``HardFilter`` renders to a Chroma ``where`` filter and a BM25 ``matches`` predicate
(see ``src/schemas.py``), so both retrievers apply the identical constraint.
"""

from __future__ import annotations

from src.schemas import HardFilter, QueryAnalysis


def build_filter(qa: QueryAnalysis) -> HardFilter:
    """QueryAnalysis -> HardFilter (company/year/quarter/form only)."""
    return HardFilter(
        tickers=qa.companies,
        years=qa.years,
        quarters=qa.quarters,
        forms=qa.forms,
    )


def describe(f: HardFilter) -> str:
    """Human-readable summary of the applied constraints (for the debug trace)."""
    parts = []
    if f.tickers:
        parts.append("company IN [" + ", ".join(f.tickers) + "]")
    if f.years:
        parts.append("year IN [" + ", ".join(str(y) for y in f.years) + "]")
    if f.quarters:
        parts.append("quarter IN [" + ", ".join(f.quarters) + "]")
    if f.forms:
        parts.append("form IN [" + ", ".join(f.forms) + "]")
    return " AND ".join(parts) if parts else "(no hard filter — search all filings)"

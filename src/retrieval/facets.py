"""Deterministic query facets and section-equivalence rules.

Facets sit between coarse intent labels and SEC section names. They let the
retrieval path say "business segments can be answered by Business OR MD&A" or
"revenue trend needs MD&A plus financial tables" without changing chunk labels
or using an LLM/NER pass.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from src.schemas import Chunk, QueryAnalysis


FACET_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("legal", (r"\blegal\b", r"\blitigation\b", r"\blawsuits?\b", r"\bproceedings?\b",
               r"\bsettlement\b", r"\bclaims?\b", r"\binvestigations?\b")),
    ("regulatory", (r"\bregulatory\b", r"\bregulation\b", r"\bcompliance\b",
                    r"\bantitrust\b", r"\bgovernment(?:al)?\b", r"\bprivacy\b")),
    ("risk", (r"\brisks?\b", r"\bheadwinds?\b", r"\buncertaint", r"\bexposure\b",
              r"\bthreats?\b", r"\bchallenges?\b")),
    ("revenue_trend", (r"\brevenue trends?\b", r"\brevenue growth\b", r"\badvertising revenue\b",
                       r"\bsubscription revenue\b", r"\bsubscriber\b", r"\bvolume and revenue\b",
                       r"\bsales growth\b", r"\bchanged? over\b", r"\bgrowth outlook\b")),
    ("financial", (r"\brevenue\b", r"\brevenues\b", r"\bsales\b", r"\bmargin\b",
                   r"\boperating income\b", r"\bnet income\b", r"\bcash flow\b",
                   r"\bprofit\b", r"\bearnings?\b", r"\beps\b", r"\bfinancial\b")),
    ("liquidity", (r"\bliquidity\b", r"\bcapital resources\b", r"\bcash requirements\b")),
    ("segments", (r"\bbusiness segments?\b", r"\boperating segments?\b", r"\bsegments?\b",
                  r"\bnorth america\b", r"\binternational\b", r"\baws\b")),
    ("business", (r"\bbusiness model\b", r"\bbusiness\b", r"\bmembership\b",
                  r"\bproducts?\b", r"\bservices?\b", r"\bstrategy\b", r"\bstrategic\b")),
    ("market_risk", (r"\bmarket risk\b", r"\binterest rate\b", r"\bforeign exchange\b",
                     r"\bcurrency\b", r"\bcommodity\b")),
)


FACET_SECTIONS: dict[str, tuple[str, ...]] = {
    "risk": ("Risk Factors",),
    "legal": ("Legal Proceedings", "Risk Factors"),
    "regulatory": ("Risk Factors", "Legal Proceedings"),
    "financial": (
        "Management's Discussion and Analysis",
        "Financial Statements and Supplementary Data",
    ),
    "revenue_trend": (
        "Management's Discussion and Analysis",
        "Financial Statements and Supplementary Data",
    ),
    "liquidity": (
        "Management's Discussion and Analysis",
        "Financial Statements and Supplementary Data",
    ),
    "segments": ("Business", "Management's Discussion and Analysis"),
    "business": ("Business", "Management's Discussion and Analysis"),
    "market_risk": (
        "Quantitative and Qualitative Disclosures About Market Risk",
        "Management's Discussion and Analysis",
    ),
}


FACET_SIGNAL_FIELDS: dict[str, tuple[str, ...]] = {
    "risk": ("has_risk_heading",),
    "legal": ("has_legal_heading",),
    "regulatory": ("has_risk_heading", "has_legal_heading"),
    "financial": ("has_financial_table", "has_revenue_table", "has_mda_heading"),
    "revenue_trend": ("has_mda_heading", "has_revenue_table", "has_financial_table"),
    "liquidity": ("has_mda_heading", "has_financial_table"),
    "segments": ("has_business_heading", "has_mda_heading"),
    "business": ("has_business_heading",),
    "market_risk": ("has_financial_table",),
}


SECTION_EQUIVALENTS: dict[str, tuple[str, ...]] = {
    "Business": ("Business", "Management's Discussion and Analysis"),
    "Management's Discussion and Analysis": (
        "Management's Discussion and Analysis",
        "Financial Statements and Supplementary Data",
    ),
    "Financial Statements and Supplementary Data": (
        "Financial Statements and Supplementary Data",
        "Management's Discussion and Analysis",
    ),
    "Risk Factors": ("Risk Factors", "Legal Proceedings"),
    "Legal Proceedings": ("Legal Proceedings", "Risk Factors"),
    "Quantitative and Qualitative Disclosures About Market Risk": (
        "Quantitative and Qualitative Disclosures About Market Risk",
        "Management's Discussion and Analysis",
    ),
}


def _unique(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(i for i in items if i))


def extract_facets(query: str, *, intents: Iterable[str] = (),
                   sections: Iterable[str] = ()) -> list[str]:
    """Map query text + existing labels to deterministic evidence facets."""
    q = query.lower()
    facets: list[str] = []
    for facet, patterns in FACET_PATTERNS:
        if any(re.search(pattern, q) for pattern in patterns):
            facets.append(facet)

    intent_set = set(intents)
    section_set = set(sections)
    if "Risk" in intent_set or "Risk Factors" in section_set:
        facets.append("risk")
    if "Financial" in intent_set or "Financial Statements and Supplementary Data" in section_set:
        facets.append("financial")
    if "Trend" in intent_set or "Temporal" in intent_set:
        if "financial" in facets:
            facets.append("revenue_trend")
    if "Legal Proceedings" in section_set:
        facets.append("legal")
    if "Business" in section_set:
        facets.append("business")
    return _unique(facets)


def sections_for_facets(facets: Iterable[str]) -> list[str]:
    """Ordered SEC sections useful for a set of facets."""
    sections: list[str] = []
    for facet in facets:
        sections.extend(FACET_SECTIONS.get(facet, ()))
    return _unique(sections)


def section_equivalents(section: str, *, facets: Iterable[str] = ()) -> tuple[str, ...]:
    """Equivalent sections for relevance/coverage; facet rules can widen them."""
    out = list(SECTION_EQUIVALENTS.get(section, (section,)))
    for facet in facets:
        if section in FACET_SECTIONS.get(facet, ()):
            out.extend(FACET_SECTIONS[facet])
    return tuple(_unique(out))


def _section_match(actual: str, target: str) -> bool:
    left = (actual or "").lower()
    right = (target or "").lower()
    return left == right or left in right or right in left


def chunk_matches_section(chunk: "Chunk", section: str, *, facets: Iterable[str] = ()) -> bool:
    """True if a chunk is in, equivalent to, or signaled for a target section."""
    equivalents = section_equivalents(section, facets=facets)
    if any(_section_match(chunk.section, target) for target in equivalents):
        return True

    section_signals = (getattr(chunk, "section_signals", "") or "").lower()
    relevant_facets = [
        facet for facet, sections in FACET_SECTIONS.items()
        if any(eq in sections for eq in equivalents)
    ]
    relevant_facets.extend(facets)
    for facet in _unique(relevant_facets):
        if any(bool(getattr(chunk, field, False)) for field in FACET_SIGNAL_FIELDS.get(facet, ())):
            return True
        if facet in section_signals:
            return True
    return False


def chunk_matches_facet(chunk: "Chunk", facet: str) -> bool:
    """True if a chunk satisfies the section or signal needs for a facet."""
    sections = FACET_SECTIONS.get(facet, ())
    if any(_section_match(chunk.section, section) for section in sections):
        return True
    if any(bool(getattr(chunk, field, False)) for field in FACET_SIGNAL_FIELDS.get(facet, ())):
        return True
    signals = (getattr(chunk, "section_signals", "") or "").lower()
    return facet in signals


def facet_coverage(chunks: Iterable["Chunk"], facets: Iterable[str]) -> dict:
    """Coverage validation for trace/debugging."""
    required = _unique(facets)
    covered = [facet for facet in required if any(chunk_matches_facet(c, facet) for c in chunks)]
    return {
        "required": required,
        "covered": covered,
        "missing": [facet for facet in required if facet not in covered],
    }


def facet_targets(qa: "QueryAnalysis") -> list[str]:
    """Facets worth enforcing in evidence selection."""
    return _unique(getattr(qa, "facets", []) or [])

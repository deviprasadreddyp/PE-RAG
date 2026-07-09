"""Stage 3 — metadata extraction (deterministic; no LLM).

Turn a validated query into a ``QueryAnalysis``: companies (tickers), years, quarters,
form types, and section intent — using regex, a company dictionary (``src/reference.py``),
and a temporal parser. Combined with the Stage-2 intent labels, plus a company-cardinality
label (Single/Multi company) derived from the number of tickers found.

Relative windows ("last two years") are intentionally NOT expanded to concrete years here —
that would require a wall-clock reference and break determinism; the retrieval planner spreads
candidates across the corpus's available years instead. Explicit years are extracted verbatim.
"""

from __future__ import annotations

import re

from src.reference import match_companies
from src.retrieval.query_classifier import classify
from src.schemas import QueryAnalysis

_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_QNUM = re.compile(r"\bQ([1-4])\b", re.I)
_QWORD = re.compile(r"\b(first|second|third|fourth)\s+quarter\b", re.I)
_QWORD_MAP = {"first": "Q1", "second": "Q2", "third": "Q3", "fourth": "Q4"}

# Section intent: keyword -> canonical SEC section name (first match wins per section).
_SECTION_KEYWORDS: list[tuple[str, list[str]]] = [
    ("Risk Factors", [r"\brisk", r"\bthreat", r"\bheadwind", r"\buncertaint", r"\bexposure\b"]),
    ("Management's Discussion and Analysis",
     [r"\bmd&?a\b", r"management(?:'s)? discussion", r"\bliquidity\b",
      r"results of operations", r"\boutlook\b", r"\bguidance\b"]),
    ("Financial Statements and Supplementary Data",
     [r"balance sheet", r"income statement", r"cash flow", r"financial statement",
      r"\bearnings\b", r"\brevenue", r"\bmargin", r"\bnet income\b", r"\bprofit"]),
    ("Business", [r"\bbusiness\b", r"\bproducts?\b", r"\bsegment", r"\bstrateg"]),
    ("Legal Proceedings", [r"\blegal\b", r"\blitigation\b", r"\blawsuit", r"\bproceeding"]),
]


def extract_years(query: str) -> list[int]:
    return sorted({int(m.group(0)) for m in _YEAR.finditer(query)})


def extract_quarters(query: str) -> list[str]:
    qs = {f"Q{m.group(1)}" for m in _QNUM.finditer(query)}
    qs |= {_QWORD_MAP[m.group(1).lower()] for m in _QWORD.finditer(query)}
    return sorted(qs)


def extract_forms(query: str) -> list[str]:
    ql = query.lower()
    forms: list[str] = []
    if re.search(r"10-?k\b", ql) or "annual report" in ql:
        forms.append("10-K")
    if re.search(r"10-?q\b", ql) or "quarterly report" in ql:
        forms.append("10-Q")
    return forms


def extract_section_intent(query: str) -> list[str]:
    ql = query.lower()
    out: list[str] = []
    for section, patterns in _SECTION_KEYWORDS:
        if any(re.search(p, ql) for p in patterns):
            out.append(section)
    return out


def parse_query(query: str) -> QueryAnalysis:
    """Full deterministic query understanding -> QueryAnalysis (Stages 2-3 combined)."""
    companies = match_companies(query)
    intents = list(classify(query))
    # company cardinality — depends on the count of extracted tickers, so decided here
    if len(companies) >= 2:
        intents.append("MultiCompany")
    elif len(companies) == 1:
        intents.append("SingleCompany")
    return QueryAnalysis(
        query=query,
        intents=intents,
        companies=companies,
        years=extract_years(query),
        quarters=extract_quarters(query),
        forms=extract_forms(query),
        section_intent=extract_section_intent(query),
    )

"""Stage 2 — query understanding: rule-based intent classification (deterministic; no LLM).

The goal is NOT to rewrite the query — it is to understand its *intent* so retrieval can be
planned (Stage 5). Multi-label: a query may be several intents at once (e.g. "how has NVIDIA's
revenue changed over two years" -> Trend + Financial + Temporal).

Company cardinality (Single vs Multi company) is intentionally NOT decided here — it depends on
the number of tickers extracted in Stage 3 — so it is added downstream from the extracted
companies. This module classifies purely from query text.
"""

from __future__ import annotations

import re

# Canonical output order. "General" is the fallback when nothing else matches.
INTENTS = ("Comparison", "Trend", "Risk", "Financial", "Temporal")

_PATTERNS: dict[str, list[str]] = {
    "Comparison": [
        r"\bcompare\b", r"\bcomparison\b", r"\bversus\b", r"\bvs\.?\b", r"\bcompared to\b",
        r"\bdifference between\b", r"\bdiffer\b", r"\bagainst\b", r"\brelative to\b",
    ],
    "Trend": [
        r"\btrend", r"\bchang", r"\bgrow", r"\bgrew\b", r"\bincreas", r"\bdecreas", r"\bdeclin",
        r"\byear[- ]over[- ]year\b", r"\byoy\b", r"\bover time\b", r"\btrajectory\b",
        r"\bhistorical\b", r"\bhow (has|have|did|do|is|are)\b", r"\bsubscription\b",
        r"\bsubscriber\b", r"\badvertising revenue\b", r"\bvolume and revenue\b",
    ],
    "Risk": [
        r"\brisk", r"\bthreat", r"\buncertaint", r"\bheadwind", r"\bchalleng", r"\bexposure\b",
    ],
    "Financial": [
        r"\brevenu", r"\bincome\b", r"\bnet income\b", r"\bprofit", r"\bmargin", r"\bearn",
        r"\beps\b", r"\bcash flow", r"\bcost", r"\bexpens", r"\bdebt\b", r"\bassets?\b",
        r"\bliabilit", r"\bsales\b", r"\bgross\b", r"\boperating\b", r"\bbalance sheet\b",
        r"\bfinancial", r"\bguidance\b", r"\bdividend", r"\badvertising\b", r"\bsubscription\b",
        r"\bsubscriber\b", r"\bvolume\b",
    ],
}

_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_QUARTER = re.compile(r"\bQ[1-4]\b", re.I)
_TEMPORAL = [
    r"\blast \w+ (year|quarter|month)", r"\bpast \w+ (year|quarter|month)", r"\brecent",
    r"\bsince\b", r"\bover the (last|past)\b", r"\bbetween\b.*\band\b", r"\bthis year\b",
]


def classify(query: str) -> list[str]:
    """Return the query's intent labels (multi-label), or ``["General"]`` if none match."""
    q = query.lower()
    labels = [intent for intent in ("Comparison", "Trend", "Risk", "Financial")
              if any(re.search(p, q) for p in _PATTERNS[intent])]
    if _YEAR.search(query) or _QUARTER.search(query) or any(re.search(p, q) for p in _TEMPORAL):
        labels.append("Temporal")
    return labels or ["General"]

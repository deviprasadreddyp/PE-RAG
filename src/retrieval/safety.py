"""Deterministic query safety checks before retrieval or generation.

These checks are intentionally plain-code guardrails. They catch prompt-injection,
credential/system-prompt exfiltration, and attempts to bypass the citation/grounding
contract before any retriever or LLM call runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyDecision:
    ok: bool
    reason: str = ""
    category: str = ""


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "instruction_override",
        re.compile(
            r"\b(ignore|disregard|forget|override|bypass)\b.{0,90}"
            r"\b(previous|prior|above|system|developer|instructions?|rules?|prompt)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "instruction_override",
        re.compile(
            r"\b(system|developer|admin)\s+(message|prompt|instructions?)\b|"
            r"\bact\s+as\s+(system|developer|admin)\b|"
            r"\bdeveloper\s+mode\b|\bjailbreak\b|\bDAN\b",
            re.IGNORECASE,
        ),
    ),
    (
        "secret_exfiltration",
        re.compile(
            r"\b(reveal|show|print|dump|leak|exfiltrate|display)\b.{0,90}"
            r"\b(system prompt|developer message|hidden prompt|instructions?|chain[- ]of[- ]thought|"
            r"secrets?|api keys?|tokens?|\.env|environment variables?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "citation_bypass",
        re.compile(
            r"\b(do not|don't|without|skip|omit|ignore)\b.{0,80}"
            r"\b(citations?|sources?|evidence|grounding)\b|"
            r"\b(make up|fabricate|invent)\b.{0,80}\b(financial|numbers?|figures?|citations?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "context_breakout",
        re.compile(
            r"</?(context|system|assistant|developer|tool|user)\b|"
            r"```+\s*(system|developer|assistant|tool)|"
            r"\bBEGIN\s+(SYSTEM|DEVELOPER|ASSISTANT)\b",
            re.IGNORECASE,
        ),
    ),
)


def evaluate_query(query: str) -> SafetyDecision:
    """Return a deterministic accept/refuse decision for user-supplied query text."""
    for category, pattern in _PATTERNS:
        if pattern.search(query):
            return SafetyDecision(
                ok=False,
                category=category,
                reason=(
                    "The question contains instructions that attempt to override the retrieval, "
                    "citation, or system-safety rules. Ask the SEC filings question directly; "
                    "I can only answer from retrieved filing evidence with citations."
                ),
            )
    return SafetyDecision(ok=True)

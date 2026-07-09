"""Stage 1 — query validation (deterministic; no LLM).

Reject malformed or meaningless queries *before* any retrieval work: empty,
too-short, too-long, control-character / bad-encoding, or content with no
alphanumeric signal. Bounds come from config (``min_query_chars`` /
``max_query_chars``). Returns a whitespace-normalized query or raises
``QueryError``.
"""

from __future__ import annotations

import re

from src.config import settings

# C0/C1 control chars except the normal whitespace (\t \n \r) — these indicate bad input.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ALNUM = re.compile(r"[A-Za-z0-9]")


class QueryError(ValueError):
    """Raised when a query is rejected before retrieval."""


def validate_query(query: str) -> str:
    """Return a cleaned (whitespace-normalized) query, or raise ``QueryError``."""
    if not isinstance(query, str):
        raise QueryError("query must be a string")
    if _CONTROL.search(query):
        raise QueryError("query contains invalid control characters")
    q = " ".join(query.split())                       # strip + collapse internal whitespace
    if not q:
        raise QueryError("query is empty")
    if len(q) < settings.min_query_chars:
        raise QueryError(f"query too short (minimum {settings.min_query_chars} characters)")
    if len(q) > settings.max_query_chars:
        raise QueryError(f"query too long (maximum {settings.max_query_chars} characters)")
    if not _ALNUM.search(q):
        raise QueryError("query has no alphanumeric content")
    return q

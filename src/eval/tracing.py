"""LangSmith tracing setup (optional observability).

If ``LANGSMITH_API_KEY`` is set, ``enable_langsmith()`` turns on LangChain's native tracing — every
``ChatOpenAI`` call (the single answer call) is then traced to LangSmith with its prompt, token
usage, and latency, grouped under the configured project. No-op (returns ``False``) when no key is
set, so nothing is required to run the system. Call it once at startup (API / eval).
"""

from __future__ import annotations

import os

from src.config import settings


def enable_langsmith(env: dict | None = None) -> bool:
    """Enable LangChain->LangSmith tracing if a key is configured. Returns whether it was enabled."""
    target = os.environ if env is None else env
    key = settings.langsmith_api_key.get_secret_value()
    if not key:
        return False
    # both the legacy (LANGCHAIN_*) and current (LANGSMITH_*) env names, so any langchain version works
    for name in ("LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING"):
        target.setdefault(name, "true")
    for name in ("LANGCHAIN_API_KEY", "LANGSMITH_API_KEY"):
        target.setdefault(name, key)
    for name in ("LANGCHAIN_PROJECT", "LANGSMITH_PROJECT"):
        target.setdefault(name, settings.langsmith_project)
    return True

"""Stage 14 — the single grounded LLM call (the ONLY generative step).

Exactly one Claude call turns the assembled prompt into a structured ``AnswerBody``. We use
LangChain ``ChatAnthropic`` with ``.with_structured_output(AnswerBody)`` — one API request that
returns the validated object (structured output uses forced tool use, so extended thinking is not
enabled here; ``temperature=0`` for grounded, reproducible answers).

Behind a ``Generator`` protocol so the pipeline and tests inject a fake (no network, no key). The
real client and its key are constructed lazily — importing this module needs neither.

Model: ``claude-opus-4-8`` (see ADR-005). Refusals never reach here — guardrails short-circuit
before generation, so a call is made only when there is trustworthy evidence.
"""

from __future__ import annotations

from typing import Protocol

from src.config import settings
from src.schemas import AnswerBody, PromptBundle


class Generator(Protocol):
    def generate(self, prompt: PromptBundle) -> AnswerBody: ...


class ClaudeGenerator:
    """Single-call Claude generator via LangChain ChatAnthropic + structured output."""

    def __init__(self, model: str | None = None, api_key: str | None = None, max_tokens: int = 1500):
        from langchain_anthropic import ChatAnthropic  # lazy: only when actually generating

        self.model = model or settings.generation_model
        llm = ChatAnthropic(
            model=self.model,
            anthropic_api_key=api_key or settings.require_anthropic_key(),
            temperature=0,
            max_tokens=max_tokens,
            timeout=60,
        )
        self._structured = llm.with_structured_output(AnswerBody)

    def generate(self, prompt: PromptBundle) -> AnswerBody:
        # exactly ONE API call
        return self._structured.invoke(
            [("system", prompt.system), ("human", prompt.user)]
        )


def generate(prompt: PromptBundle, *, generator: Generator | None = None) -> AnswerBody:
    """Run the single grounded call (constructs a ClaudeGenerator by default)."""
    return (generator or ClaudeGenerator()).generate(prompt)

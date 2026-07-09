"""Stage 14 — the single grounded LLM call (the ONLY generative step).

Exactly one call turns the assembled prompt into a structured ``AnswerBody``. Generation goes
through **OpenRouter** (OpenAI-compatible) using LangChain ``ChatOpenAI`` pointed at OpenRouter's
base URL, with ``.with_structured_output(AnswerBody)`` — one API request that returns the validated
object (``temperature=0`` for grounded, reproducible answers).

Behind a ``Generator`` protocol so the pipeline and tests inject a fake (no network, no key). The
real client and its key are constructed lazily — importing this module needs neither.

Model: ``openai/gpt-4o`` via OpenRouter (see ADR-014). Refusals never reach here — guardrails
short-circuit before generation, so a call is made only when there is trustworthy evidence.
"""

from __future__ import annotations

from typing import Protocol

from src.config import settings
from src.schemas import AnswerBody, PromptBundle


class Generator(Protocol):
    def generate(self, prompt: PromptBundle) -> AnswerBody: ...


class OpenRouterGenerator:
    """Single-call generator via an OpenAI-compatible model on OpenRouter (ChatOpenAI + base_url)."""

    def __init__(self, model: str | None = None, api_key: str | None = None, max_tokens: int = 1500):
        from langchain_openai import ChatOpenAI  # lazy: only when actually generating

        self.model = model or settings.generation_model
        llm = ChatOpenAI(
            model=self.model,
            api_key=api_key or settings.require_openrouter_key(),
            base_url=settings.openrouter_base_url,
            temperature=0,
            max_tokens=max_tokens,
            timeout=60,
            default_headers={"X-Title": "PE-RAG"},   # optional OpenRouter attribution
        )
        self._structured = llm.with_structured_output(AnswerBody)

    def generate(self, prompt: PromptBundle) -> AnswerBody:
        # exactly ONE API call
        return self._structured.invoke(
            [("system", prompt.system), ("human", prompt.user)]
        )


def generate(prompt: PromptBundle, *, generator: Generator | None = None) -> AnswerBody:
    """Run the single grounded call (constructs an OpenRouterGenerator by default)."""
    return (generator or OpenRouterGenerator()).generate(prompt)

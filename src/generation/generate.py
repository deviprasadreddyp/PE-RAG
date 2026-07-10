"""Stage 14 - the single grounded LLM call (the ONLY generative step).

Exactly one call turns the assembled prompt into a structured ``AnswerBody``. Generation uses
OpenAI's Responses API with Structured Outputs, so the model returns a validated object instead of
free-form text that we need to parse heuristically.

Behind a ``Generator`` protocol so the pipeline and tests inject a fake (no network, no key). The
real client and its key are constructed lazily; importing this module needs neither.

Model: direct OpenAI ``gpt-5.5`` by default. Refusals never reach here: guardrails short-circuit
before generation, so a call is made only when there is trustworthy evidence.
"""

from __future__ import annotations

from typing import Protocol

from src.config import settings
from src.schemas import AnswerBody, PromptBundle


class Generator(Protocol):
    def generate(self, prompt: PromptBundle) -> AnswerBody: ...


class OpenAIGenerator:
    """Single-call generator via OpenAI Responses API + Structured Outputs."""

    def __init__(self, model: str | None = None, api_key: str | None = None,
                 max_output_tokens: int | None = None):
        from openai import OpenAI  # lazy: only when actually generating

        self.model = model or settings.generation_model
        self.max_output_tokens = max_output_tokens or settings.generation_max_output_tokens
        self._client = OpenAI(api_key=api_key or settings.require_openai_key(), timeout=90)

    def generate(self, prompt: PromptBundle) -> AnswerBody:
        # exactly ONE API call
        response = self._client.responses.parse(
            model=self.model,
            instructions=prompt.system,
            input=prompt.user,
            text_format=AnswerBody,
            text={"verbosity": settings.generation_verbosity},
            reasoning={"effort": settings.generation_reasoning_effort},
            max_output_tokens=self.max_output_tokens,
            store=False,
        )

        parsed = getattr(response, "output_parsed", None)
        if parsed is not None:
            return parsed

        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                parsed = getattr(content, "parsed", None)
                if parsed is not None:
                    return parsed

        text = getattr(response, "output_text", "")
        return AnswerBody.model_validate_json(text)


def generate(prompt: PromptBundle, *, generator: Generator | None = None) -> AnswerBody:
    """Run the single grounded call (constructs an OpenAIGenerator by default)."""
    return (generator or OpenAIGenerator()).generate(prompt)

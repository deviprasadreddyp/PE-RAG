"""Stage 13 — prompt builder (deterministic; no LLM).

Assemble the single-call prompt: a stable SYSTEM prompt (cite-or-refuse rules) + a USER message
(LangChain ``PromptTemplate``) with the ``<context>`` evidence block, the question, and the output
format. The prompt is **versioned** (``PROMPT_VERSION``) so every logged answer records which
prompt produced it. ``fit_to_budget`` trims lowest-ranked evidence so the input stays within the
token budget (§10); a rough chars/4 estimate avoids a tokenizer dependency.
"""

from __future__ import annotations

from langchain_core.prompts import PromptTemplate

from src.retrieval.evidence_builder import render_context
from src.schemas import Evidence, PromptBundle, QueryAnalysis

PROMPT_VERSION = "v1"

_MAX_INPUT_TOKENS = 7300        # §10 budget: system + instructions + evidence + question
_CHARS_PER_TOKEN = 4            # rough estimate (no tokenizer dependency)
_PER_EVIDENCE_OVERHEAD = 30     # header/tag tokens per evidence block
_INSTRUCTION_OVERHEAD = 80      # output-format + framing tokens

SYSTEM = (
    "You are a financial-analysis assistant for a private-equity firm. Answer ONLY from the SEC "
    "filing excerpts provided in <context>. Rules:\n"
    "- Ground every claim in the context and cite the evidence id(s) it came from, e.g. [E1].\n"
    "- Preserve numbers, units ($, thousands, millions), signs, and fiscal periods EXACTLY.\n"
    "- Distinguish companies and periods; never attribute one company's figure to another.\n"
    '- If the context does not contain the answer, say "Information unavailable in the provided '
    'filings."\n'
    "- Output the sections defined in Output format."
)

_USER = PromptTemplate.from_template(
    "<context>\n{context}\n</context>\n\n"
    "Question: {question}\n\n"
    "Output format: Executive Summary; Comparison (if applicable); Supporting Evidence "
    "(each fact with its [E#] citation); Citations; Confidence; Limitations."
)


def _estimate_tokens(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


def fit_to_budget(evidence: list[Evidence], question: str, *, max_input_tokens: int = _MAX_INPUT_TOKENS
                  ) -> list[Evidence]:
    """Keep as many best-first evidence blocks as fit the input token budget (>=1)."""
    used = _estimate_tokens(SYSTEM) + _estimate_tokens(question) + _INSTRUCTION_OVERHEAD
    kept: list[Evidence] = []
    for e in evidence:                                       # best-first
        cost = _estimate_tokens(e.chunk.text) + _PER_EVIDENCE_OVERHEAD
        if kept and used + cost > max_input_tokens:
            break
        kept.append(e)
        used += cost
    return kept


def build_prompt(qa: QueryAnalysis, evidence: list[Evidence]) -> PromptBundle:
    """Render the SYSTEM + USER prompt for the given (already budget-fit) evidence."""
    user = _USER.format(context=render_context(evidence), question=qa.query)
    return PromptBundle(system=SYSTEM, user=user, prompt_version=PROMPT_VERSION)

---
name: llm-pipeline-reviewer
description: Review the generation side of an LLM/RAG pipeline — prompt design, grounding, structured outputs, schema validation, JSON parsing robustness, streaming, retries, fallbacks, and refusal behavior. Use when building or auditing the answer-generation path, prompt templates, or any code that calls an LLM and parses its output. Check the claude-api skill before writing Claude API calls.
---

# LLM Pipeline Reviewer

The generation stage turns retrieved context into an answer. Review it for correctness under the
reality that model outputs are non-deterministic and occasionally malformed.

## When to invoke
- Building/auditing prompt templates, the answer generator, or any LLM-calling code.
- Adding structured output, streaming, or output parsing.

> Before writing or reviewing actual Claude API calls (model IDs, params, tool use, caching,
> structured output), consult the **`claude-api`** skill — don't rely on memory for API details.

## Review dimensions

**Prompt design**
- Clear role/system boundary. Task, constraints, and output format stated explicitly.
- **Grounding**: "answer only from the provided context; if it's not there, say you don't know."
  Context is clearly delimited from instructions (defense against prompt injection in filings).
- **Cite-or-refuse**: require citations to the provided chunks; refuse when unsupported.
- Few-shot examples where format/behavior needs pinning. Context ordered best-first within budget.

**Structured output & parsing**
- Use the provider's structured-output / tool-schema mechanism rather than hoping for clean JSON.
- Validate every output against a schema (e.g. Pydantic). Never `eval` model output.
- Robust parsing: handle extra prose, markdown fences, trailing commas, partial JSON. Fail loud,
  not silent, on invalid output — then retry or fall back.

**Reliability of the call** (coordinate with `reliability-engineer`)
- Retries with backoff on transient errors (429/5xx/timeouts); cap attempts; jitter.
- Timeouts on every call. Idempotency where a retry could double-charge or double-write.
- Fallbacks: smaller/faster model, degraded answer, or a clean error — never a hang or a lie.

**Streaming**
- If streaming to a user, handle mid-stream errors and incomplete final chunks. Don't commit a
  partial structured result as if complete.

**Determinism & cost**
- Temperature appropriate to the task (low for extraction/grounded QA). Prompts not needlessly
  huge (→ `cost-optimizer`). Prompt caching for stable prefixes.

**Safety**
- Retrieved/user text can't override the system prompt. Model output that renders as HTML/MD is
  sanitized. No secrets in prompts or logs.

## Output
Findings per dimension with concrete fixes, and the riskiest failure mode (malformed output,
injection, silent truncation) called out first with its mitigation.

# Skill: single-call-rag

**Purpose.** Produce the final answer from **exactly one Claude API request** with the retrieved
context injected. This is the assessment's hard constraint and non-negotiable rule #1.

**When to invoke.** Work in `src/generation/answer.py` — the one place the answer is generated.

> Consult the installed **`claude-api`** skill for exact model IDs, params, and the single-call
> pattern before writing this. Do not code the API call from memory.

## Ground rules
- **One `client.messages.create()` for the answer.** Retrieval, query parsing, reranking, and
  context assembly all happen BEFORE it and may use other models/calls. The *answer* is one call.
- **Model:** `claude-opus-4-8` for the final answer (demo quality; 1M context). Cheaper stages
  (rerank, query rewrite) may use `claude-sonnet-5` / `claude-haiku-4-5`.
- **Inject context in the message, not by chaining calls.** The stable system prompt (the grounded
  instructions from `prompt-template`) + the assembled context + the question go into one request.
- **Prompt caching:** put the stable system prompt first with a `cache_control` breakpoint; the
  per-query context and question go after it. Repeated demo questions then reuse the cached prefix.
- **Return a typed result:** `Answer{answer: str, sources: list[Citation], usage: dict}`. Surface
  `usage` (tokens, cost) to the front-end.

## Bad example
```python
# BAD: two LLM calls on the answer path — violates the single-call rule
summary = client.messages.create(model="claude-opus-4-8", messages=[{"role":"user",
            "content": f"Summarize these filings:\n{context}"}])          # call 1
final   = client.messages.create(model="claude-opus-4-8", messages=[{"role":"user",
            "content": f"Using this summary answer: {summary}\nQ:{q}"}])   # call 2  ✗
```

## Good example
```python
def answer(question: str) -> Answer:
    results = retrieve(question)                       # pre-call: retrieval (may use other models)
    context, citations = assemble(results)            # pre-call: assembly
    resp = client.messages.create(                    # THE single answer call
        model="claude-opus-4-8",
        max_tokens=2000,
        system=[{"type": "text", "text": GROUNDED_SYSTEM_PROMPT,   # stable → cacheable
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user",
                   "content": f"<context>\n{context}\n</context>\n\nQuestion: {question}"}],
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return Answer(answer=text, sources=used_citations(text, citations),
                  usage=resp.usage.model_dump())
```

## Failure modes seen
- A "summarize then answer" or "map-reduce over filings" pattern sneaks in a second LLM call.
- An agent/tool loop that calls the model multiple times to assemble the answer.
- Context passed as a separate prior turn and then a second call made — still two calls.
- Model chosen by cost, not by the rule (skill default is `claude-opus-4-8` for the final answer).

## MUST NOT
- MUST NOT make more than one Claude call to produce the answer.
- MUST NOT hide a second LLM call inside retrieval/rerank/"summarize" and call the result one call.
- MUST NOT hardcode the API key (`ANTHROPIC_API_KEY` from env).
- MUST NOT return raw model text without attaching the sources it cited.

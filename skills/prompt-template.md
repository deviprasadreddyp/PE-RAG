# Skill: prompt-template

**Purpose.** Define and version the grounded, cite-or-refuse prompt used in the single call, and keep
the iteration log the assessment requires.

**When to invoke.** Work in `src/generation/prompt.py`; any change to prompt wording.

## The template (structure)
Keep the system prompt stable (for caching) and put context + question in the user turn.
```
SYSTEM (stable, cacheable):
  You are a financial analyst assistant for a private-equity firm. Answer the question using ONLY
  the SEC filing excerpts provided in <context>. Rules:
  - Ground every claim in the context. If the context does not contain the answer, say exactly what
    is missing and do not guess.
  - Preserve numbers, units ($, thousands, millions), signs, and fiscal periods EXACTLY as written.
  - Cite each claim inline with the bracket tag of the excerpt it came from,
    e.g. "[AAPL 10-K FY2024 · Item 7 MD&A]".
  - Structure the answer for a busy analyst: a one-line takeaway, then concise supporting points;
    for comparisons use a short table or parallel bullets per company.
  - Distinguish companies and periods carefully; never attribute one company's figure to another.

USER (per query):
  <context> {assembled, citation-tagged chunks} </context>
  Question: {question}
```

## Rules
- **Delimit context clearly** (`<context>…</context>`) and instruct "use only the context" — this is
  also the defense against prompt injection in filing text (`answer-grounding`).
- **Version it.** `PROMPT_VERSION = "vN"` constant in `prompt.py`. Every change bumps it and appends
  to `prompt_iterations/CHANGELOG.md`: what changed, why, and the effect on the eval metrics.
- **Iterate against the eval set,** not one example. Change one thing at a time (`skills/evaluation`).

## prompt_iterations/CHANGELOG.md entry format
```
## v3 — 2026-07-09
Changed: added "preserve units and fiscal periods exactly" line.
Why: v2 sometimes rounded revenue and dropped "$ in millions".
Effect: numeric-fidelity on eval set 0.78 → 0.95; faithfulness unchanged.
```

## Bad example
```python
# BAD: unversioned f-string, no grounding/refusal, context and instructions blur together
prompt = f"Answer this using the filings: {context}. Question: {q}"   # invites hallucination
# ...edited in place next week with no record of what changed or why
```

## Good example
```python
PROMPT_VERSION = "v3"
GROUNDED_SYSTEM_PROMPT = textwrap.dedent(""" ...rules above... """).strip()
def build_user_turn(context: str, question: str) -> str:
    return f"<context>\n{context}\n</context>\n\nQuestion: {question}"
```

## Failure modes seen
- Prompt edited in place with no changelog entry → the required iteration log is missing/unreliable.
- Instructions and context concatenated with no delimiter → model treats filing text as instructions.
- "Be helpful" phrasing without an explicit refusal clause → the model guesses on thin context.
- No "preserve numbers/units/period" line → figures get rounded or units dropped.

## MUST NOT
- MUST NOT ship a prompt change without a `prompt_iterations/CHANGELOG.md` entry.
- MUST NOT omit the grounding + cite-or-refuse instructions.
- MUST NOT tune the prompt on a single anecdote instead of the eval set.

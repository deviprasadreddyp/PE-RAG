# 01 — Product Spec: <feature name>

> Fill this out FIRST, before any design or code. Answer every question explicitly; if an answer is
> "unknown," say so and flag it as a question for the human. Keep it under one page.
> Copy this file to `features/active/<feature-name>/01-product-spec.md` and fill it in.

## Problem
- **What business question does this feature help answer?** (one sentence)
- **Who asks it?** (the PE analyst persona / demo audience)
- **What triggered this feature?** (gap in current behavior, demo requirement, bug)

## Query types in scope
Which of these does this feature serve? (tick all that apply, add examples)
- [ ] Single-company lookup ("What was NVIDIA's FY2024 revenue?")
- [ ] Cross-company comparison ("Compare risk factors: Apple vs Tesla vs JPMorgan")
- [ ] Cross-period trend ("How has NVIDIA's growth outlook changed over 2 years?")
- [ ] Sector / thematic ("What regulatory risks do major pharma companies face?")
- [ ] Definitional / qualitative

## Success criteria (measurable)
- **Answer quality:** e.g. faithfulness ≥ X on the eval set; every claim cited.
- **Retrieval quality:** e.g. recall@k ≥ X for the target query type.
- **Latency budget:** end-to-end target for the single call + retrieval (seconds).
- **Cost ceiling:** target tokens / $ per query.
- **Refusal correctness:** unanswerable questions must be refused, not guessed.

## Hidden requirements (make them explicit)
- Citations required? At what granularity (filing / section / passage)?
- Numeric fidelity: must figures + units + fiscal period be preserved verbatim? (For finance: yes.)
- Scope filters the user can express (ticker, form 10-K/10-Q, fiscal period range)?
- Freshness: static corpus, or must new-filing ingestion be handled?

## Edge cases to handle
- No matching filing for the requested company/period.
- Ambiguous ticker or company name.
- Question spanning multiple companies or periods (needs fan-out retrieval).
- A number that appears in the wrong company's / period's chunk.
- Empty retrieval result.

## Assumptions
- List each assumption. Mark **confirmed** or **needs confirmation**.

## Out of scope
- What this feature will explicitly NOT do (prevent scope creep).

## Open questions for the human
- Batch the load-bearing unknowns here. Do not proceed to the technical spec until answered.

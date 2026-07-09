---
name: requirements-analyzer
description: Clarify a task before designing or coding it — surface the real problem, hidden and non-functional requirements, edge cases, assumptions, and missing information. Use at the very start of any non-trivial feature, task, or bug fix, before architecture-designer or any implementation. Especially for RAG features where "answer questions over filings" hides dozens of decisions (which periods? which companies? citations? freshness?).
---

# Requirements Analyzer

Before a single line of design or code, pin down what is actually being asked. Most
implementation defects are requirements defects in disguise.

## When to invoke
- A feature or task is requested in one sentence ("add filtering by company").
- A bug report is vague ("retrieval is bad").
- Before `architecture-designer` / `implementation-planner`.

## Process
Answer these explicitly and write them down. Do not silently assume.

1. **The real problem.** What outcome does the user actually want? Restate it in one sentence.
   What triggered the request? Who is the user of this feature?
2. **Functional requirements.** Enumerate concrete behaviors. Inputs, outputs, actions.
3. **Non-functional requirements.** Latency budget, throughput, cost ceiling, accuracy target,
   availability, security/compliance, observability. Put numbers on them.
4. **Hidden requirements.** What's implied but unsaid? (e.g. "search filings" implies
   metadata filtering, citations, handling companies with no filing for a period.)
5. **Edge cases.** Empty input, no results, multiple matches, stale data, huge input,
   conflicting filings, missing fiscal period, ambiguous ticker.
6. **Assumptions.** List every assumption. Mark each as "confirmed" or "needs confirmation."
7. **Missing information.** What do you not know that changes the design? Batch these into a
   short question list — ask the user rather than guessing on load-bearing unknowns.
8. **Out of scope.** State what this task will NOT do, to prevent scope creep.

## RAG / SEC-domain prompts to always ask
- Which query types? (single-company lookup, cross-company comparison, cross-period trend, definitional.)
- What's the scope filter — ticker(s), form type (10-K vs 10-Q), fiscal period range?
- Are citations required? At what granularity (filing / section / passage)?
- Numeric fidelity: must exact figures + units + period be preserved verbatim?
- Freshness: is the corpus static, or does new-filing ingestion need to be handled?
- What's an acceptable "I don't know" vs a hallucinated answer? (For finance, refusing beats guessing.)

## Output
A short **Requirements Brief**: Problem · Functional · Non-functional · Edge cases ·
Assumptions (confirmed/open) · Out of scope · Open questions for the user. Keep it tight.
Do not proceed to design until open load-bearing questions are answered.

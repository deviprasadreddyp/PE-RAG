# evals/ — Proof the harness works

> Scott's rule: **your harness is code — run evals on it.** Without evals you're just hoping.

An eval takes a task, hands it to a **fresh** coding-tool chat with **only this harness loaded**, and
compares the output to what a correct build/answer should look like. If it matches (architecture,
conventions, rules), the harness works. If it diverges, `result-notes.md` tells you exactly which
skill or rule was missing — sharpen it and re-run.

## Two kinds of eval here

- **Build evals** — "add feature X." Pass = the tool follows the template sequence (PRD → tech spec →
  plan → build), uses the right skills, respects the non-negotiable rules, and matches our conventions
  and folder layout. (e.g. `case-04`.)
- **Behavior evals** — run a real business question through the built system. Pass = correct
  retrieval (right filings/period), a grounded + cited answer with exact numbers, and a refusal when
  the corpus can't answer. (e.g. `case-01/02/03/05`.)

## How to run an eval

1. Start a **fresh** chat in Claude Code / Cursor (no existing thread — `agents.md` is the context).
2. Load the harness: point the tool at `agents.md`.
3. Paste the contents of the case's `prompt.md`. Treat it as a real request.
4. Let it run end-to-end **without interventions or clarifying answers**.
5. Compare the output to `expected.md`.
6. Write findings in `result-notes.md`: what happened vs expected, and which skill/rule needs work.
7. Update the failing skill/rule and re-run.

## What "passing" means

- Followed the sequence (product spec → technical spec → implementation plan → build) for build evals.
- Used the right skills — no invented conventions (own chunking, own vector store, extra LLM call).
- Did not violate any non-negotiable rule in `agents.md` §9 — especially **single LLM call**,
  **cite-or-refuse**, **no fabricated data**, **no hardcoded keys**, **strip XBRL**.
- Generated code matches the existing style, folder layout, and the `Chunk`/`Answer` contracts.
- Minimal back-and-forth — ideally zero.

## Readiness bar

If fewer than **2 of these 5 cases pass**, the harness is not ready. Sharpen skills, re-run, iterate.

## Cases

| Case | Stresses |
|---|---|
| `case-01-multi-company-risk-comparison` | multi-ticker metadata filter, fan-out retrieval, comparison structure, cite-or-refuse (also the **example request**) |
| `case-02-revenue-trend-nvidia` | cross-period retrieval, fiscal-period filtering, numeric fidelity |
| `case-03-pharma-regulatory-risk` | sector/thematic retrieval with no explicit ticker, cross-company synthesis |
| `case-04-add-fiscal-period-filter` | **build eval** — template sequence, `metadata-schema` + `hybrid-retrieval` skills, re-index discipline |
| `case-05-unanswerable-refusal` | grounding / refusal on a filing not in the corpus (no hallucination) |

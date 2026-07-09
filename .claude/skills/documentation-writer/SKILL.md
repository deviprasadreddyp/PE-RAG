---
name: documentation-writer
description: Produce clear documentation — README, architecture overview, API reference, meaningful code comments, and design-decision/tradeoff records (ADRs). Use after a component stabilizes, when onboarding docs are missing, or when a non-obvious decision should be recorded. Document the "why," not the obvious "what."
---

# Documentation Writer

Good docs answer the questions the next engineer (or future you) will actually have. Explain
intent and tradeoffs; let the code speak for mechanics.

## When to invoke
- A component/API stabilizes and needs a reference.
- The repo lacks a usable README or setup guide.
- A non-obvious decision was made and should be recorded before the reasoning is forgotten.

## What to write (pick what's missing)

**README** — what this is, why it exists, how to run it.
- One-paragraph purpose · prerequisites · setup (env vars, secrets, install) · how to ingest the
  corpus · how to run a query · how to run tests. Keep the quick-start truly quick.

**Architecture overview** — the module map, data/control flow (a diagram), and the contracts
between ingestion, retrieval, and generation. Link to the design doc from `architecture-designer`.

**API reference** — for each endpoint/function: purpose, params/types, response schema, error
shapes/codes, and an example request/response. Keep it consistent across endpoints.

**Code comments** — explain *why*, not *what*. Comment surprising choices, invariants,
workarounds, and units (e.g. "figures in USD thousands, per filing"). Match the surrounding
comment density. Delete comments that just restate the code.

**Design decisions (ADRs)** — for each significant choice: context, options considered, decision,
consequences, and when to revisit. Capture the output of `tradeoff-analyzer` so the "why"
survives. One short file per decision.

## Principles
- Accurate over comprehensive — wrong docs are worse than none. Update docs with the code.
- Show, don't just tell: runnable examples beat prose.
- Write for the reader's task, not the writer's mental model.
- Don't document what the code already makes obvious.

## Output
The doc(s) in the right place (README at root, ADRs under `docs/decisions/`, etc.), factual and
example-driven, with any assumptions the reader must know stated up front.

---
name: implementation-planner
description: Break an approved design into ordered, independently testable and committable phases so work proceeds incrementally without going off the rails. Also serves as task decomposer and progress tracker. Use after architecture-designer and before writing implementation code, or whenever a large task needs to be sequenced. Pairs with the built-in TodoWrite for live tracking.
---

# Implementation Planner

Convert a design into a sequence of small phases. Each phase must stand on its own.

## When to invoke
- After `architecture-designer`, before coding.
- Any task large enough that "just start coding" would drift.

## Rules for a good plan
- **Each phase is independently testable** — it has a clear "done" check you can run.
- **Each phase is independently committable** — it leaves the repo in a working state.
- **Order by dependency and risk.** Do the riskiest/most-uncertain thing early (a spike) so
  surprises surface before you've built on top of them.
- **Vertical slices over horizontal layers** where possible — a thin end-to-end path beats
  a fully-built layer that can't be exercised yet.
- **Small.** If a phase can't be described in a sentence and tested in isolation, split it.

## Process
1. List the phases in order. For each: goal, files/modules touched, the test that proves it,
   and the commit message it earns (hand to `git-commit-writer`).
2. Mark dependencies between phases.
3. Call out the first "walking skeleton" — the smallest end-to-end slice that runs.
4. Note what is explicitly deferred to a later phase.

## Example — SEC RAG MVP
```
Phase 0  Spike: load 3 filings, strip XBRL, print clean body        → eyeball output
Phase 1  Ingestion contract: Chunk model + metadata extractor       → unit tests on filenames/headers
Phase 2  Chunker: section-aware split, table-preserving             → tests on known filings
Phase 3  Embed + upsert to vector store (small subset)              → count + spot-check vectors
Phase 4  Retrieval: metadata filter + top-k dense search           → recall on a hand-labeled query set
Phase 5  Generation: grounded prompt, cite-or-refuse, structured   → faithfulness eval on Q&A pairs
Phase 6  Hybrid + rerank                                            → retrieval-evaluator shows lift
Phase 7  Full-corpus ingest + API endpoint                         → end-to-end latency/cost check
```

## Output
An ordered phase list (goal · files · test · commit · deps), the walking-skeleton call-out,
and deferred items. Offer to load it into TodoWrite for tracking. Keep phases shippable.

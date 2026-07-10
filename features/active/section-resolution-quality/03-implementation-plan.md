# 03 - Implementation Plan: Section Resolution Quality

## Build Order

### Phase 0 - Spike
- **Goal:** encode deterministic weak-label and strong-heading rules.
- **Files:** `src/pipeline/section_resolution.py`, tests.
- **Proof:** unit tests for J&J legal, UPS MD&A, weak summary labels, and no-op canonical sections.
- **Skill:** `section-detection`, `metadata-schema`.
- **Commit:** `feat(section): add deterministic section resolver`

### Phase 1 - Data Model / Chunking
- **Goal:** attach section confidence, source, signals, and metadata quality to chunks on future rebuilds.
- **Files:** `src/schemas.py`, `src/pipeline/chunk.py`, tests.
- **Proof:** chunk creation populates fields and preserves original text.
- **Skill:** `chunking-strategy`, `metadata-schema`.
- **Commit:** `feat(chunk): persist section signal metadata`

### Phase 2 - Retrieval
- **Goal:** use runtime resolution for existing artifacts and signal-aware section boosting/evidence selection.
- **Files:** `src/retrieval/vector_retriever.py`, `metadata_parser.py`, `retrieval_planner.py`, `retrieval_pipeline.py`, tests.
- **Proof:** query parsing boosts MD&A and financial statements for trend/revenue; evidence selection prefers signaled sections.
- **Skill:** `hybrid-retrieval`.
- **Commit:** `feat(retrieval): prefer section-resolved evidence`

### Phase 3 - Evaluation Hygiene
- **Goal:** remove or mark impossible stale JPM case so refusal is not penalized.
- **Files:** `src/eval/datasets/golden.jsonl`.
- **Proof:** eval case is marked as expected refusal or updated to available corpus.
- **Skill:** `evaluation`.
- **Commit:** `test(eval): fix unavailable filing case`

## Migrations / Re-Index
This changes chunk metadata and retrieval behavior. Code is safe against existing artifacts, but full benefit requires rerunning chunk -> enrich -> embed -> store. Per user instruction, do not run or mutate those artifacts yet.

## Walking Skeleton
Hydrate a current retrieved chunk, resolve `Exhibits` or `Form 10-K Summary` to the stronger detected section in memory, and use that section in final evidence.

## Deferred
Full rebuild and metric comparison are deferred until the user approves.

## Definition Of Done
- [x] No extra LLM calls introduced.
- [x] Existing artifacts are not rewritten.
- [ ] Focused tests pass.
- [ ] Full eval after approved rebuild shows improved section-sensitive metrics.

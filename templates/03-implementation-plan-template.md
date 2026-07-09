# 03 — Implementation Plan: <feature name>

> Fill this out AFTER the technical spec. Break the work into ordered, independently testable and
> committable phases. Then tell the coding tool: "Build this implementation plan."
> Copy this file to `features/active/<feature-name>/03-implementation-plan.md`.

## Build order (bottom-up: data → index → retrieval → API → UI)
Each phase: goal · files touched · the test that proves it · the skill it follows · commit message.
Order by dependency and risk; do the riskiest/unknown thing first as a spike.

### Phase 0 — Spike (de-risk the unknown)
- **Goal:** smallest thing that proves the approach (e.g. parse 3 filings, print clean sectioned text).
- **Files:** …
- **Proof:** eyeball output / a scratch assertion.
- **Skill:** …

### Phase 1 — Data model / ingestion
- **Goal:** e.g. metadata extraction + XBRL strip for the target filings.
- **Files:** `src/ingest/parser.py`, tests.
- **Proof:** unit tests on known filenames/headers; no XBRL in output.
- **Skill:** `document-ingestion`, `metadata-schema`.
- **Commit:** `feat(ingest): ...`

### Phase 2 — Index
- **Goal:** chunk → embed → upsert (subset first).
- **Files:** `src/ingest/chunker.py`, `src/index/embedder.py`, `src/index/store.py`.
- **Proof:** chunk-count + spot-check vectors; tables intact; re-run is idempotent.
- **Skill:** `chunking-strategy`, `embedding-generation`.
- **Commit:** `feat(index): ...`

### Phase 3 — Retrieval
- **Goal:** metadata filter + hybrid search + rerank.
- **Files:** `src/retrieval/retriever.py`, `src/retrieval/context.py`.
- **Proof:** recall@k on the hand-labeled eval set (`skills/evaluation`).
- **Skill:** `hybrid-retrieval`, `context-assembly`.
- **Commit:** `feat(retrieval): ...`

### Phase 4 — Generation (the single call)
- **Goal:** grounded prompt + one Claude call → answer + citations.
- **Files:** `src/generation/prompt.py`, `src/generation/answer.py`, `prompt_iterations/CHANGELOG.md`.
- **Proof:** faithfulness + citation-accuracy + refusal on unanswerable; **exactly one** API call.
- **Skill:** `single-call-rag`, `prompt-template`, `answer-grounding`.
- **Commit:** `feat(generation): ...`

### Phase 5 — Front-end / wiring
- **Goal:** Streamlit input → answer + sources + retrieved chunks + latency/cost.
- **Files:** `frontend/app.py`, `README.md`.
- **Proof:** end-to-end run of the example question; latency/cost within budget.
- **Skill:** `frontend-streamlit`.
- **Commit:** `feat(app): ...`

## Migrations / re-index
- Does this change the chunk schema or embedding model? If yes: bump the collection name / version,
  re-run `scripts/build_index.py`, and note the re-index in the plan (old vectors are not compatible).

## Walking skeleton
Name the first end-to-end slice that runs (e.g. 3 filings → retrieve → single call → answer in UI).

## Deferred
What is intentionally left for a later feature.

## Definition of done
- [ ] All phases' tests pass (with real output shown, not assumed).
- [ ] Non-negotiable rules in `agents.md` §9 respected (esp. single call, cite-or-refuse, no fake data).
- [ ] Prompt change (if any) logged in `prompt_iterations/CHANGELOG.md`.
- [ ] Example request runs end to end in the front-end.

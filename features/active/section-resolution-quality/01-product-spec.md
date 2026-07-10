# 01 - Product Spec: Section Resolution Quality

## Problem
- **Business question:** Help PE analysts retrieve the right SEC filing evidence when the semantic content is present but the original section label is noisy or wrong.
- **Who asks it:** PE analyst / CTO demo audience validating trust, citations, and explainability.
- **Trigger:** Eval failures showed correct-looking evidence labeled as `Exhibits`, `Other`, `Form 10-K Summary`, or `Directors...`, causing strict section-based retrieval metrics to fail.

## Query Types In Scope
- [x] Single-company lookup: "What legal proceedings is Johnson & Johnson involved in?"
- [x] Cross-company comparison: section labels must remain reliable when evidence is balanced per company.
- [x] Cross-period trend: revenue/growth trend queries need MD&A plus financial statement coverage.
- [x] Sector / thematic: regulatory/legal/risk themes need robust section signals.
- [x] Definitional / qualitative: business model questions need `Business` and MD&A detection.

## Success Criteria
- **Answer quality:** retrieved evidence should carry accurate section/citation metadata.
- **Retrieval quality:** improve hit@k on section-sensitive eval failures after rebuild.
- **Latency budget:** deterministic regex/signal checks only; no new LLM calls.
- **Cost ceiling:** no new API cost.
- **Refusal correctness:** keep refusal behavior for genuinely unavailable company/form/year filters.

## Hidden Requirements
- Citations stay filing/section/passages grounded.
- Numeric text and financial tables remain verbatim.
- Metadata values must be Chroma-safe scalars.
- Existing artifacts must not be mutated until the user explicitly requests rechunk/re-embed/re-store.

## Edge Cases
- Chunk text includes a real section heading inside a weak parent section.
- TOC text mentions many section names but is not body evidence.
- Financial tables live under exhibits or summary labels.
- Query asks for a filing/year that is absent from the corpus.

## Assumptions
- **Confirmed:** No LLM is allowed for section correction.
- **Confirmed:** Current embeddings are good enough; section metadata is the bottleneck.
- **Confirmed:** This implementation may change code/tests now, but must not rewrite `data/chunks`, `data/embeddings`, Chroma, or BM25 yet.

## Out Of Scope
- No embedding model change.
- No prompt change.
- No data rebuild until explicitly requested.

## Open Questions
- None blocking.

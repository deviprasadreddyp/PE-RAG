# 03 - Implementation Plan: Full Rechunk + Full Index

## Build order

### Phase 0 - Spike
- **Goal:** Inspect real raw files and confirm XBRL/header shape.
- **Files:** none.
- **Proof:** sample raw inspection shows downloader header plus compressed XBRL preamble.
- **Skill:** `document-cleaning`, `metadata-schema`.

### Phase 1 - Metadata and cleaning
- **Goal:** Preserve useful XBRL/cover facts as metadata and strip XBRL infrastructure safely.
- **Files:** `src/schemas.py`, `src/pipeline/metadata.py`, `src/pipeline/clean.py`, tests.
- **Proof:** unit tests pass; sample metadata contains fiscal focus/amendment fields; cleaned text has no XBRL tag soup.
- **Skill:** `document-cleaning`, `metadata-schema`.
- **Commit:** `feat(pipeline): preserve xbrl metadata and clean tag soup`

### Phase 2 - Chunking
- **Goal:** Rechunk within sections with stronger table preservation and contextual table headers.
- **Files:** `src/pipeline/chunk.py`, `src/pipeline/enrich.py`, tests.
- **Proof:** chunk tests verify no cross-section chunks, table rows remain intact, and metadata is complete.
- **Skill:** `chunking-strategy`, `chunk-enrichment`.
- **Commit:** `feat(index): improve sec chunking quality`

### Phase 3 - Full rebuild
- **Goal:** Regenerate clean/metadata/sections/chunks/enriched chunks, then embed every chunk and store all vectors/BM25 entries.
- **Files:** `data/*` artifacts.
- **Proof:** final counts show Chroma vectors == BM25 docs == chunk count.
- **Skill:** `embedding-generation`, `hybrid-retrieval`.
- **Commit:** `chore(index): rebuild full corpus index`

### Phase 4 - Evals
- **Goal:** Expand deterministic eval cases and rerun quality metrics.
- **Files:** `src/eval/datasets/golden.jsonl`, `data/logs/eval_report.*`.
- **Proof:** eval dashboard/report reflects new cases and full dense coverage.
- **Skill:** `evaluation`.
- **Commit:** `test(eval): expand rag quality cases`

## Migrations / re-index
Chunk text and metadata change, so stale `data/embeddings` and `data/vectorstore` must be cleared before the full embedding/store run. The embedding cache may stay because keys include model and embed text.

## Walking skeleton
One filing through clean -> metadata -> sections -> chunks -> enrich, spot-check text and metadata, then full corpus.

## Deferred
- Full XBRL numeric fact warehouse.
- Query-time amended-filing preference policy beyond metadata availability.

## Definition of done
- [ ] Tests pass.
- [ ] Full chunks embedded with OpenAI.
- [ ] Chroma vector count equals regenerated chunk count.
- [ ] BM25 count equals regenerated chunk count.
- [ ] Eval dataset expanded and ready to rerun.

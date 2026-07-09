# Assumptions & Design Decisions

Dedicated record of the assumptions the system is built on. Each is a deliberate, defensible choice;
where the data drove it, the source is cited.

## Data & corpus
- **Corpus scope:** 246 filings (10-K/10-Q) from ~54 large-cap US companies, 2022–2026. Questions
  outside this corpus are **refused, not guessed**.
- **Filenames are authoritative for discovery** (via `manifest.json`); the **header is authoritative
  for metadata**, with the filename backfilling `fiscal_period` when the header lacks it
  (`Report Period`/`Quarter` present on only ~78% of filings — see `corpus_notes.md`).
- **`filing_date` ≠ `fiscal_period`.** We filter on `fiscal_period` (what the filing covers), not the
  filing date. Fiscal year ≠ calendar year.

## Cleaning
- **XBRL-strip boundary:** the leading XBRL/us-gaap machine blob is removed by anchoring on the first
  prose marker (`UNITED STATES … SEC` / `FORM 10-K/Q`); verified to remove `us-gaap:` from all 246
  filings while preserving numbers, units, and tables.
- **Current cleaning is on the "aggressive" side** (blob-cut + tag-line removal). The refined design
  prefers *controlled normalization* (remove only isolated metadata lines) and a *Normalization vs
  Structural Parsing* split — tracked as an open decision in `DESIGN_AUDIT.md` (Part A).

## Chunking
- **Dataset-driven size:** fixed **3000-char / 300-overlap** window, split **within** sections. The
  filings have ~no blank-line paragraphs (median 1/filing), so paragraph chunking isn't viable; size
  is char-based (not token-based) and is a starting point to be tuned by the retrieval eval.
- **Section-aware hierarchy:** sections are parents, chunks are children; each chunk records
  `section_index` and `section_chunk_index`. Section detection is best-effort (92% of filings) with a
  graceful "Other" fallback so nothing is lost.

## Identity, determinism, idempotency
- **Chunk IDs are deterministic and section-aware** (`{doc_id}__{Section}_c{NN}`), not random UUIDs —
  reproducible, debuggable, and cache/incremental-friendly.
- **Deterministic except generation.** No LLM in ingestion, metadata, sectioning, chunking,
  retrieval, or citations — only the single answer call is model-driven.
- **No wall-clock/random in artifacts** (so re-runs are byte-identical); re-runs upsert by id and
  skip already-current stages.

## Embeddings & retrieval
- **Embeddings:** OpenAI `text-embedding-3-large`, batched (100) with 3 retries (exponential backoff),
  content-hash cached. Behind an `Embedder` protocol (Voyage/local are drop-in alternatives).
- **Hybrid retrieval:** hard metadata filters first, then BM25 + vector fused with RRF (`k=60`,
  rank-only, no score normalization). See `PHYSICAL_SPEC.md` §5.

## Generation (Phase 2)
- **Single Claude call** (`claude-opus-4-8`) produces the answer.
- **Cite-or-refuse:** every claim cited to `[Ticker Form Period · Section] · chunk_id`; if the context
  is insufficient the system says "Information unavailable in the provided filings."
- **Confidence** is deterministic (mean top-k similarity → High/Medium/Low), no LLM.

## Operational
- **Error isolation:** one corrupt filing is dead-lettered per stage and skipped, never aborting the
  other 245.
- **Secrets** come only from `.env` (git-ignored). The **dataset is not committed** (obtained
  separately); only `manifest.json` is tracked.

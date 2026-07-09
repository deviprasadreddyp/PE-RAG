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
- **Semantic hierarchy, not fixed size:** sections are the semantic unit (parents); within each
  section the recursive splitter packs boundary-preserving pieces **up to a MAX cap** of
  **3000 chars / 300 overlap**. The cap is a *ceiling, not a target* — short sections stay whole
  (one small chunk), long ones split only at real boundaries. Verified on the corpus: ~98% of a
  filing's chunks land **below** the cap (avg ~2300 chars), which is the signature of variable,
  content-driven sizing rather than a fixed window.
- **Char-based cap** (~750 tokens, not token-based): the filings have ~no blank-line paragraphs
  (median 1/filing), so paragraph chunking isn't viable; the cap is a starting point tuned by eval.
- **Section-aware hierarchy:** sections are parents, chunks are children; each chunk records
  `section_index` and `section_chunk_index`, plus a `content_hash` (sha256 of its text) for
  content-addressed dedup. Section detection is best-effort (92% of filings), canonicalized to the
  standard SEC names + Part tree for 10-K, with a graceful "Other" fallback so nothing is lost.

## Identity, determinism, idempotency
- **Chunk IDs are deterministic and section-aware** (`{doc_id}__{Section}_c{NN}`), not random UUIDs —
  reproducible, debuggable, and cache/incremental-friendly.
- **Deterministic except generation.** No LLM in ingestion, metadata, sectioning, chunking,
  retrieval, or citations — only the single answer call is model-driven.
- **No wall-clock/random in artifacts** (so re-runs are byte-identical); re-runs upsert by id and
  skip already-current stages.

## Embeddings & retrieval
- **Embeddings:** local `BAAI/bge-large-en-v1.5` (sentence-transformers, 1024-dim, cosine-normalized;
  query gets the bge instruction prefix), batched + content-hash cached. Behind an `Embedder` protocol
  (any provider is a drop-in). No API key. See ADR-013.
- **Reranking:** local cross-encoder `BAAI/bge-reranker-base` (`-large` optional), identity fallback.
- **Hybrid retrieval:** hard metadata filters first, then BM25 + vector fused with RRF (`k=60`,
  rank-only, no score normalization). See `PHYSICAL_SPEC.md` §5.

## Generation
- **Single LLM call** — `openai/gpt-4o` via **OpenRouter** (ChatOpenAI + base_url, structured output)
  produces the answer. `OPENROUTER_API_KEY` is the only key the system needs. See ADR-014.
- **Cite-or-refuse:** every claim cited to `[Ticker Form Period · Section] · chunk_id`; if the context
  is insufficient the system says "Information unavailable in the provided filings."
- **Confidence** is deterministic (mean top-k similarity → High/Medium/Low), no LLM.

## Operational
- **Error isolation:** one corrupt filing is dead-lettered per stage and skipped, never aborting the
  other 245.
- **Secrets** come only from `.env` (git-ignored). The **dataset is not committed** (obtained
  separately); only `manifest.json` is tracked.

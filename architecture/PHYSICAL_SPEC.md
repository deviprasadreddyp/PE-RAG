# Physical Implementation Specification

The concrete "how" — exact modules, data models, config, storage schema, algorithms (with
formulae), policies, and logging. Companion to `HLD.md` (logical) and `ARCHITECTURE.md` (business).
Items marked **(Phase 2)** are specified here but not yet built.

## 1. Project structure

```
src/
  config.py            # typed settings (pydantic-settings)
  schemas.py           # data models (see §2)
  observability.py     # persist/load artifacts, per-stage error isolation (run_docs)
  run.py               # orchestrator CLI
  inspect.py           # stage inspection report
  pipeline/            # offline stages, one module per stage
    ingest.py clean.py metadata.py sections.py chunk.py enrich.py embed.py store.py
  retrieval/           # (Phase 2) parse.py · search.py · fuse.py · context.py
  generation/          # (Phase 2) prompt.py · generate.py
scripts/               # inspect_corpus.py · build_index.py
data/                  # raw cleaned metadata sections chunks embeddings vectorstore logs  (git-ignored)
frontend/              # (Phase 2) app.py (Streamlit, normal + debug mode)
evaluation/            # (Phase 2) eval_set.jsonl + metrics
```

> Concern-oriented naming maps 1:1 to the pipeline; `pipeline/` groups the ingest stages, `retrieval/`
> and `generation/` hold Phase 2. (A finer split into `normalization/ metadata/ sections/ …` is a
> possible future refactor — see DESIGN_AUDIT #20.)

## 2. Data models (`src/schemas.py`)

| Model | Status | Fields |
|---|---|---|
| `DocMetadata` | ✅ | company, ticker, form, filing_date, source_file, report_period, fiscal_period, year, quarter, cik, source_url |
| `SectionSpan` | ✅ | section_name, item, start, end |
| `Chunk` (⊃ DocMetadata) | ✅ | id, doc_id, chunk_index, section, section_index, section_chunk_index, text, embed_text |
| `Citation` | ✅ | tag, ticker, company, form, fiscal_period, section, source_url |
| `RetrievalResult` | ✅ | chunk, score |
| `Answer` | ✅ | answer, sources[Citation], retrieved[RetrievalResult], usage |
| `EmbeddingRecord` | ⚠️ dict today | {chunk_id, embedding, metadata} — planned to become a typed model |
| `Document` | ⚠️ implicit | doc_id + DocMetadata (+ planned sha256) — not a standalone class yet |

All chunk metadata is Chroma-safe (str/int/float/bool, no None, no lists). `extra="forbid"` everywhere.

## 3. Configuration (`src/config.py`, env / `.env`)

`openai_api_key`, `anthropic_api_key` (SecretStr) · `embedding_model=text-embedding-3-large` ·
`generation_model=claude-opus-4-8` · `chunk_max_chars=3000` (per-chunk MAX cap), `chunk_overlap=300` (chars) ·
`vector_top_k=20`, `bm25_top_k=20`, `rrf_k=60`, `candidate_pool=30`, `rerank_top_k=8`, `min_similarity=0.35` · `embed_batch_size=100`, `embed_max_retries=3` ·
`data_dir`, `corpus_dir`, `chroma_dir`, `collection_base`. `collection_name` = `{base}__{model}`.

## 4. Storage schema

**Chroma** collection `sec_filings__text-embedding-3-large` (cosine): each record =
`id` (chunk_id) · `embedding` · `document` (original text) · `metadata` (ticker/company/form/
fiscal_period/year/quarter/section/section_index/source_url/…). *(Planned add: `hash`; `created_at`
is intentionally omitted for deterministic artifacts.)*

**BM25** `data/vectorstore/bm25.json`: `{ids, tokens, metadatas}` (tokenizer: lowercase `[a-z0-9]+`).

## 5. Retrieval pipeline (Phase 2)

```
question
  → parse metadata filters (deterministic: tickers, years, quarter, form)     [HARD filters]
  → BM25 search (top 20, within filter)         ┐
  → vector search (top 20, within filter)        ├─ both are SOFT semantic/lexical ranking
  → Reciprocal Rank Fusion (RRF)                ┘
  → deduplicate (by doc_id + section + chunk_index)
  → take top 8
  → context builder (order best-first, tag citations, fit token budget)
  → single Claude call
```

**Hard filters vs soft retrieval.** *Hard filters* (company/year/quarter/form) are exact metadata
constraints applied **before** ranking — they cannot be traded off (an "AAPL 2024 10-K" question must
never return TSLA). *Soft retrieval* (BM25 + vector) ranks by relevance **within** the hard-filtered
set. This split is why metadata is a first-class, indexed field on every chunk.

**Reciprocal Rank Fusion.** For each candidate document *d*, over ranked lists *r ∈ {BM25, vector}*:

```
score(d) = Σ_r  1 / (k + rank_r(d))          k = 60 (constant), rank_r 1-based; d absent from a list contributes 0
```

Chosen because it fuses lists using only **ranks**, so it needs **no score normalization** across the
(incomparable) BM25 and cosine scales, and it is robust to outliers. `k=60` is the standard default.

## 6. Prompt template (Phase 2) — `src/generation/prompt.py`

```
SYSTEM (stable, cache-controlled):
  You are a financial-analysis assistant for a private-equity firm. Answer ONLY from the SEC filing
  excerpts in <context>. Rules:
  - Ground every claim in the context; cite the excerpt it came from.
  - Preserve numbers, units ($, thousands, millions), signs, and fiscal periods EXACTLY.
  - Distinguish companies and periods; never attribute one company's figure to another.
  - If the context does not contain the answer, say "Information unavailable in the provided filings."
  - Output the sections defined in "Output format".

USER:
  <context>
  [AAPL 10-K FY2024 · Item 1A Risk Factors] (chunk AAPL_10K_2024...__RiskFactors_c03)
  <chunk text>
  ---
  [TSLA 10-K FY2024 · Item 1A Risk Factors] (chunk TSLA_10K_2024...__RiskFactors_c01)
  <chunk text>
  </context>

  Question: {question}

  Output format: Executive Summary · Comparison · Supporting Evidence · Citations · Confidence
```

Exactly **one** `client.messages.create()` produces the answer.

## 7. Output schema (Phase 2)

The single call returns markdown with these sections (mapped to the `Answer` model):
1. **Executive Summary** — 1–3 sentence takeaway.
2. **Comparison** — per-company / per-period table or parallel bullets (for comparison questions).
3. **Supporting Evidence** — the specific facts/figures, each with an inline citation.
4. **Citations** — the list of sources (see §8), linking `source_url`.
5. **Confidence** — High / Medium / Low (see §9).

## 8. Citation format

Inline tag → section → chunk id, e.g.:

```
[Apple 10-K FY2024] · Risk Factors · chunk AAPL_10K_2024Q4_2024-11-01__RiskFactors_c03
```

Every citation resolves to a retrieved chunk; the `Citation` model carries ticker/company/form/
fiscal_period/section/source_url so the front-end can render a link.

## 9. Confidence score (Phase 2, no LLM)

Deterministic from retrieval: `avg_sim` = mean cosine similarity of the top-k retrieved chunks
(similarity = 1 − distance). `High ≥ 0.75 · Medium 0.55–0.75 · Low < 0.55` (thresholds tunable via
the eval set). A refusal ("Information unavailable") always reports **Low**.

## 10. Policies

- **Embedding requests** — batch `embed_batch_size` (100) per call; `embed_max_retries` (3) with the
  OpenAI SDK's exponential backoff on 429/5xx. Content-hash cache avoids re-embedding.
- **Generation retry (Phase 2)** — Anthropic SDK auto-retries 429/5xx with backoff; one logical call.
- **Error isolation** — every per-doc stage isolates failures (`observability.run_docs`): a bad
  filing is dead-lettered to `data/logs/<stage>_failures.json` and skipped, never aborting the rest.
- **Idempotency** — upsert by `chunk_id`; stages skip when their artifact is current (orchestrator).

## 11. Log taxonomy (`data/logs/`)

| Log | Content | Status |
|---|---|---|
| **Pipeline logs** | per-stage `<stage>_failures.json` (dead-lettered docs) | ✅ |
| **Query logs** (Phase 2) | per query: question, filters, retrieved chunk ids, scores, prompt, response, latency, tokens, cost, timestamp | ❌ |
| **Application logs** | operational stdout/stderr (run/inspect summaries) | ⚠️ (print-based) |
| **Evaluation logs** (Phase 2) | per eval case: expected vs retrieved, metric values | ❌ |

## 12. Cost & latency tracking (Phase 2)

Per query, record embedding tokens (query), generation input/output tokens, `$` cost (from model
pricing), and wall-clock latency into the `Answer.usage` object and the query log. Surfaced in the
debug UI.

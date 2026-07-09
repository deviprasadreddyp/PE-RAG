# PE-RAG

An **observable ingestion & retrieval pipeline** that answers a private-equity analyst's
natural-language question over **SEC EDGAR filings** (10-K / 10-Q) and returns a structured,
grounded, cited answer from a **single LLM API call** (OpenAI models via OpenRouter).

We don't "build a RAG" — we build an observable pipeline where **every stage persists an
inspectable artifact**, all processing is **deterministic except the one generation call**, and the
whole system is traceable end to end.

> **Status.** Both phases are **built and tested** (209 tests): the offline **ingestion & indexing
> pipeline** (Stages 1–8) and the online **retrieval + single-call generation** layer (validation →
> query understanding → hybrid retrieval → RRF → rerank → guardrails → one LLM call → cited
> answer), plus per-query logging, an eval harness, a FastAPI service, and a Streamlit debug UI.
> Embeddings and the reranker are **local** (`sentence-transformers`, no key); the single answer
> call goes through **OpenRouter** (`OPENROUTER_API_KEY`). The only **deferred** steps need
> compute/keys: the real embed/store run and a live generation call. See
> `architecture/RETRIEVAL_DESIGN.md` and `ADR.md`.

## The one hard rule

Indexing and retrieval run **beforehand**; the final answer comes from **exactly one LLM API
request** (OpenAI via OpenRouter). Everything expensive — cleaning, metadata, sectioning, chunking,
embedding, retrieval, reranking — happens before that single call, and is deterministic or local ML.

## Architecture

```
OFFLINE (python -m src.run --stage all) — one inspectable artifact per stage:
 edgar_corpus/*.txt
   → ingest   → data/raw/         validated, unmodified
   → clean    → data/cleaned/     strip XBRL blob + artifacts; keep business text + tables
   → metadata → data/metadata/    deterministic: header + filename (header wins)
   → sections → data/sections/    detect Item headings -> {section_name, item, start, end}
   → chunk    → data/chunks/       section-aware hierarchical chunks (recursive, within sections)
   → enrich   → data/chunks/       prepend Company|Filing|Year|Section as embed_text
   → embed    → data/embeddings/   local BAAI/bge-large-en-v1.5, batched, content-hash cached
   → store    → data/vectorstore/  Chroma (vectors + text + metadata) + BM25 index

ONLINE (src/retrieval/retrieval_pipeline.py) — per question, no LLM until the last step:
 question → validate → classify + extract metadata → hard filter → plan
          → hybrid retrieve (vector top-20 + BM25 top-20) → RRF (k=60) → rerank (top-8)
          → dedup → evidence [E1..] → guardrails (cite-or-refuse)
          → ONE LLM call (GPT via OpenRouter, grounded, structured) → answer + citations → data/logs/queries.jsonl
```

Everything left of the single call is deterministic or local ML; refusals (invalid query, weak
evidence, missing company) make **zero** LLM calls.

Design docs: [`architecture/RETRIEVAL_DESIGN.md`](architecture/RETRIEVAL_DESIGN.md) (Phase 2 TDS) ·
[`architecture/ADR.md`](architecture/ADR.md) (decision records) ·
[`architecture/HLD.md`](architecture/HLD.md) ·
[`architecture/CHUNKING_STRATEGY.md`](architecture/CHUNKING_STRATEGY.md) ·
[`architecture/corpus_notes.md`](architecture/corpus_notes.md) (dataset findings).

## Pipeline stages

| # | Stage | Module | Output | Notes |
|---|-------|--------|--------|-------|
| 1 | ingest | `src/pipeline/ingest.py` | `data/raw/` | manifest-driven, validated, byte-faithful; dead-letters failures |
| 2 | clean | `src/pipeline/clean.py` | `data/cleaned/` | strip XBRL/us-gaap blob; preserve numbers/tables |
| 3 | metadata | `src/pipeline/metadata.py` | `data/metadata/` | header wins over filename; backfills fiscal period |
| 4 | sections | `src/pipeline/sections.py` | `data/sections/` | inline `Item N.` headings; 92% detected, graceful "Other" fallback |
| 5 | chunk | `src/pipeline/chunk.py` | `data/chunks/` | recursive splitting **within** sections (parent→child) |
| 6 | enrich | `src/pipeline/enrich.py` | `data/chunks/` | `embed_text` = `Company (Ticker) \| Filing \| Year \| Quarter \| Section` + text (idempotent) |
| 7 | embed | `src/pipeline/embed.py` | `data/embeddings/` | local `BAAI/bge-large-en-v1.5` (sentence-transformers), batched + cached |
| 8 | store | `src/pipeline/store.py` | `data/vectorstore/` | Chroma upsert (idempotent) + BM25 |

Orchestrator: `src/run.py`. Inspection: `src/inspect.py`. Corpus spike: `scripts/inspect_corpus.py`.

### Online — retrieval & generation (`src/retrieval/`, `src/generation/`)

| Stage | Module | Role |
|-------|--------|------|
| validate | `query_validator.py` | reject empty / too-short / too-long / bad-encoding |
| classify | `query_classifier.py` | rule-based multi-label intent (Comparison/Trend/Risk/Financial/Temporal) |
| extract | `metadata_parser.py` | companies (ticker dict) · years · quarters · forms · section intent |
| filter | `metadata_filter.py` | hard metadata filter (Chroma `where` + BM25 predicate) |
| plan | `retrieval_planner.py` | per-entity / per-period / global + section boosts |
| retrieve | `vector_retriever.py`, `bm25_retriever.py` | dense + sparse, within the hard filter |
| fuse | `hybrid_fusion.py` | Reciprocal Rank Fusion (`Σ 1/(k+rank)`, k=60) |
| rerank | `reranker.py` | local cross-encoder (optional; identity fallback) |
| dedup | `deduplicator.py` | drop dup content; cap per section for diversity |
| evidence | `evidence_builder.py` | `[E1..]` grounding blocks + citation tags |
| guardrails | `guardrails.py` | coverage · diversity · min-similarity · cite-or-refuse |
| prompt | `prompt_builder.py` | system (cite-or-refuse) + evidence + question, token-budgeted, versioned |
| **generate** | `src/generation/generate.py` | **the single LLM call** — GPT via OpenRouter (structured output) |
| parse/cite | `response_parser.py`, `citation_mapper.py` | structured answer + resolved citations |

Orchestrator: `src/retrieval/retrieval_pipeline.py` (`run_query`). Serving: `src/api/main.py`
(FastAPI). UI: `src/frontend/app.py` (Streamlit). Eval: `src/eval/` (metrics + golden set).

## Stack

Python 3.11+ · **LangChain** (`RecursiveCharacterTextSplitter`, Chroma retriever, `PromptTemplate`,
`ChatOpenAI` structured output — infrastructure only, no Chains/Agents) · `chromadb` · `rank-bm25` ·
embeddings **local `BAAI/bge-large-en-v1.5`** (`sentence-transformers`, behind an `Embedder`
protocol) · reranker **local `BAAI/bge-reranker-base`** (`-large` optional; identity fallback) ·
generation **`openai/gpt-4o` via OpenRouter** (single structured call) · **FastAPI** + **Streamlit** ·
`pydantic-settings` · `pytest`.

## Getting the corpus

The dataset (246 `.txt` filings + `manifest.json`, ~79 MB) is **not** committed. Obtain
`edgar_corpus.zip` from the assessment and unzip into `edgar_corpus/` at the repo root. The tracked
`edgar_corpus/manifest.json` lists the expected files.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # add OPENROUTER_API_KEY (the single answer call); embeddings are local

# Build the index (all 8 stages, in order, idempotent)
python -m src.run --stage all          # or: python scripts/build_index.py
#   All 8 stages run locally with NO API key (embeddings are local bge); needs sentence-transformers.

# Inspect any stage — counts, samples, and sanity checks over the whole pipeline
python -m src.inspect

# Browse the intermediate artifacts directly
ls data/raw data/cleaned data/metadata data/sections data/chunks data/embeddings data/vectorstore
```

### Ask questions (Phase 2)

```bash
# FastAPI service — POST /query, GET /health, ?debug for the full stage trace
uvicorn src.api.main:app --reload          # docs at http://127.0.0.1:8000/docs

# Streamlit debug UI — answer + every deterministic stage, with clickable citations
streamlit run src/frontend/app.py

# Evaluation over the golden set — retrieval A/B + metrics (+ optional RAGAS)
python -m src.eval.run_eval                 # writes data/logs/eval_report.{json,html}
streamlit run src/eval/dashboard.py         # visual dashboard (after a run)
```

### Evaluation — "how do you know it works?"

A first-class evaluation framework (`src/eval/`, see [`architecture/EVALUATION.md`](architecture/EVALUATION.md)):
- **Golden set** of 25 business questions with metadata ground truth (+ 2 refusal cases).
- **Retrieval metrics** (Recall@k, Precision@k, MRR, NDCG@k) and an **A/B harness** that proves
  hybrid + rerank beat vector- or BM25-only *with numbers* (pooled recall).
- **RAGAS** generation grading (faithfulness, answer_relevancy, context precision/recall) — grader
  LLM via OpenRouter, embeddings local. Optional (`pip install ragas langchain-huggingface`).
- **LangSmith** tracing (prompt/tokens/latency) — on when `LANGSMITH_API_KEY` is set.
- **Reports** (`eval_report.json` + `.html`) with a **regression** diff vs the previous run, and a
  **Streamlit dashboard**. Every metric/report/regression function is pure and unit-tested; live
  grading is gated on the built index + keys.

Both need the index built (stages 7–8) and the relevant API key; without them the pipeline
returns a grounded refusal rather than crashing.

### Docker

```bash
python -m src.run --stage all     # 1. build the index locally (no key; needs sentence-transformers)
cp .env.example .env              # 2. add OPENROUTER_API_KEY (the single answer call)
docker compose up --build         # 3. serve the API at http://localhost:8000/docs
```

The image contains only code + deps (`sentence-transformers` stays optional, so it's lean); the
built index (`data/`) and corpus are mounted at runtime and keys come from `.env`. A `HEALTHCHECK`
hits `/health`.

### Useful commands

```bash
python -m src.run --stage sections                       # run one stage over every filing
python -m src.run --stage clean --doc-id AAPL_10K_2022Q3_2022-10-28   # one stage, one filing
python -m src.run --stage all --force                    # ignore "already current", redo
python -m src.pipeline.clean                             # run a stage standalone
python scripts/inspect_corpus.py                         # regenerate architecture/corpus_notes.md
python -m pytest                                         # 209 tests
```

## Observability

Every offline stage writes to `data/<stage>/<doc_id>.<ext>` via `src/observability.py`, so you can
open any intermediate output and see exactly what a stage produced. If cleaning removed too much,
chunking mixed sections, or metadata is wrong — you inspect the artifact and know precisely where.
`python -m src.inspect` turns this into a one-command health check (and exits non-zero on failure).

## Assumptions & decisions

- **Deterministic except generation.** Cleaning, metadata, section detection, chunking, retrieval,
  and citations are plain code. An LLM is used **only** for the final answer (Phase 2, one call).
- **Chunking = Section-Aware Hierarchical Chunking.** Sections are parents; chunks are children split
  **within** each section with a recursive boundary-preserving splitter. Size is a **MAX cap** (3000
  chars / 300 overlap), not a fixed target — short sections stay whole; ~98% of chunks land below the
  cap. Char-based (not tokens): the filings have almost no blank-line paragraphs (median 1 per
  filing), so paragraph chunking isn't viable; see `architecture/corpus_notes.md`.
- **Metadata: header wins over filename.** Fields come from the filing header; the filename backfills
  `fiscal_period` when absent (`Report Period`/`Quarter` are present on only ~78% of filings). `form`
  is normalized to exactly `10-K` / `10-Q`. Never uses an LLM.
- **Cleaning strips the XBRL blob** by anchoring on the first prose marker
  (`UNITED STATES … SEC` / `FORM 10-K/Q`) — verified to remove `us-gaap:` from all 246 filings while
  preserving numbers, units, and tables.
- **Section detection is best-effort with a safe fallback.** Inline `Item N. Title` headings are
  detected across the nbsp (10-K) and pipe (10-Q) layouts, excluding cross-references and the TOC;
  92% of filings parse into sections, the rest fall back to a single "Other" span so nothing is lost.
- **Idempotent & cached.** Re-runs upsert by stable `chunk_id`; embeddings are cached by
  `sha256(model + embed_text)`, so identical chunks and re-runs are never re-embedded.
- **Corpus scope.** 246 filings (10-K/10-Q) from ~54 large-cap US companies, 2022–2026. Questions
  outside this corpus should be **refused, not guessed** (Phase 2 grounding).

## Deliverables map (assessment ↔ repo)

| Deliverable | Where |
|---|---|
| README with setup/run | this file |
| Indexing code | `src/pipeline/`, `src/run.py`, `scripts/build_index.py` |
| Retrieval code | `src/retrieval/` (validate → … → RRF → rerank → guardrails → evidence) |
| Final prompt template | `src/retrieval/prompt_builder.py` (versioned) |
| Single-call generation | `src/generation/generate.py` |
| Front-end | `src/frontend/app.py` (Streamlit) · `src/api/main.py` (FastAPI) |
| Example request | `evals/case-01-.../prompt.md` |
| Quality evaluation | `src/eval/` (metrics + golden set) · `src/inspect.py` |

## Secrets

API keys come from `.env` (git-ignored) — never hardcoded or committed.

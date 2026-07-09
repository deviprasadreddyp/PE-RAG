# PE-RAG

An **observable ingestion & retrieval pipeline** that answers a private-equity analyst's
natural-language question over **SEC EDGAR filings** (10-K / 10-Q) and returns a structured,
grounded, cited answer from a **single Claude API call**.

We don't "build a RAG" — we build an observable pipeline where **every stage persists an
inspectable artifact**, all processing is **deterministic except the one generation call**, and the
whole system is traceable end to end.

> **Status.** The offline **ingestion & indexing pipeline (Stages 1–8) is built and tested**
> (82 passing tests). Retrieval, the single Claude call, per-query logging, and the FastAPI/Streamlit
> front-end are **Phase 2** (see `architecture/INGESTION_COMMIT_PLAN.md`).

## The one hard rule

Indexing and retrieval run **beforehand**; the final answer comes from **exactly one Claude API
request**. Everything expensive — cleaning, metadata, sectioning, chunking, embedding, retrieval —
happens before that single call.

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
   → embed    → data/embeddings/   OpenAI text-embedding-3-large, batched, content-hash cached
   → store    → data/vectorstore/  Chroma (vectors + text + metadata) + BM25 index

ONLINE (Phase 2) — per question, no LLM until the last step:
 question → metadata filter → hybrid retrieve (dense + BM25 → RRF) → context
          → ONE Claude call (grounded, cite-or-refuse) → answer + citations → data/logs/
```

Design docs: [`architecture/HLD.md`](architecture/HLD.md) ·
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
| 6 | enrich | `src/pipeline/enrich.py` | `data/chunks/` | `embed_text` = context header + text (idempotent) |
| 7 | embed | `src/pipeline/embed.py` | `data/embeddings/` | OpenAI `text-embedding-3-large`, batched + cached |
| 8 | store | `src/pipeline/store.py` | `data/vectorstore/` | Chroma upsert (idempotent) + BM25 |

Orchestrator: `src/run.py`. Inspection: `src/inspect.py`. Corpus spike: `scripts/inspect_corpus.py`.

## Stack

Python 3.11+ · **LangChain** (`RecursiveCharacterTextSplitter`, `OpenAIEmbeddings`, Chroma) ·
`chromadb` · `rank-bm25` · embeddings **OpenAI `text-embedding-3-large`** (behind an `Embedder`
protocol; Voyage/local are documented alternatives) · generation **Claude `claude-opus-4-8`** (single
call, Phase 2) · FastAPI + Streamlit (Phase 2) · `pydantic-settings` · `pytest`.

## Getting the corpus

The dataset (246 `.txt` filings + `manifest.json`, ~79 MB) is **not** committed. Obtain
`edgar_corpus.zip` from the assessment and unzip into `edgar_corpus/` at the repo root. The tracked
`edgar_corpus/manifest.json` lists the expected files.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # add OPENAI_API_KEY (embeddings) and ANTHROPIC_API_KEY (Phase 2)

# Build the index (all 8 stages, in order, idempotent)
python -m src.run --stage all          # or: python scripts/build_index.py
#   Stages 1–6 are deterministic and need no key; stage 7 (embed) needs OPENAI_API_KEY.

# Inspect any stage — counts, samples, and sanity checks over the whole pipeline
python -m src.inspect

# Browse the intermediate artifacts directly
ls data/raw data/cleaned data/metadata data/sections data/chunks data/embeddings data/vectorstore
```

### Useful commands

```bash
python -m src.run --stage sections                       # run one stage over every filing
python -m src.run --stage clean --doc-id AAPL_10K_2022Q3_2022-10-28   # one stage, one filing
python -m src.run --stage all --force                    # ignore "already current", redo
python -m src.pipeline.clean                             # run a stage standalone
python scripts/inspect_corpus.py                         # regenerate architecture/corpus_notes.md
python -m pytest                                         # 82 tests
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
  **within** each section with a recursive boundary-preserving splitter. Size **3000 chars / 300
  overlap** — a **dataset-driven** choice: the filings have almost no blank-line paragraphs (median 1
  per filing), so paragraph chunking isn't viable; see `architecture/corpus_notes.md`.
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
| Indexing & retrieval code | `src/pipeline/`, `src/run.py`, `scripts/build_index.py` (retrieval: Phase 2) |
| Prompt iteration log | `prompt_iterations/CHANGELOG.md` (Phase 2) |
| Final prompt template | `src/generation/prompt.py` (Phase 2) |
| Front-end | `frontend/app.py` (Phase 2) |
| Example request | `evals/case-01-.../prompt.md` |
| Quality evaluation notes | `evaluation/` + `src/inspect.py` |

## Secrets

API keys come from `.env` (git-ignored) — never hardcoded or committed.

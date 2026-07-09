# PE-RAG

Retrieval-Augmented Generation over **SEC EDGAR filings** (10-K annual + 10-Q quarterly reports)
that answers a natural-language **business question** and returns a **structured, grounded, cited
answer produced by a single LLM API call** — built for a private-equity use case.

> **Status:** this repo currently contains the **build harness** (see below). The application
> pipeline (`src/`) and the Streamlit front-end (`frontend/app.py`) are built *using* the harness.

## The one hard rule

Indexing and retrieval run **beforehand**; the final answer comes from **exactly one Claude API
request**. Everything expensive — embedding, retrieval, reranking, query parsing, context assembly —
happens before that single call.

## What's in here

This project is driven by an agent **harness** — the reusable context that makes a coding tool
(Claude Code / Cursor) build the system the intended way instead of improvising.

```
agents.md            ← master file: architecture, stack, rules, skill glossary (read this first)
DESIGN_DOC.md        ← what the harness is and how to use it
templates/           ← the feature workflow: product spec → tech spec → implementation plan
skills/              ← opinionated how-tos (ingestion, chunking, retrieval, the single call, …)
evals/               ← proof the harness works: rebuild a feature, compare to expected
prompt_iterations/CHANGELOG.md ← the prompt iteration log
src/             ← application code (ingest / index / retrieval / generation / eval) — built via the harness
frontend/app.py               ← Streamlit front-end — built via the harness
edgar_corpus/        ← dataset (git-ignored; only manifest.json is tracked — see below)
```

## Architecture

```
 OFFLINE:  edgar_corpus/*.txt → load → strip XBRL → section-aware chunk → embed → Chroma + BM25
 ONLINE:   question → metadata filter (ticker/form/period) → hybrid retrieve → rerank → assemble
                                                                                     │
                                              ONE Claude call (grounded, cite-or-refuse) → answer + sources
```

## Planned stack (pinned in `agents.md`)

Python 3.11+ · embeddings **Voyage `voyage-finance-2`** (local `bge-small` fallback) · vector store
**Chroma** (metadata filtering) · **dense + BM25** fused with RRF · generation **Claude
`claude-opus-4-8`** (single call) · **Streamlit** front-end.

## Getting the corpus

The dataset (246 `.txt` filings + `manifest.json`, ~79 MB) is **not** committed. Obtain
`edgar_corpus.zip` from the assessment and unzip it into `edgar_corpus/` at the repo root. The
tracked `edgar_corpus/manifest.json` lists the expected files and describes the corpus.

## Setup (once the pipeline is built)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # add ANTHROPIC_API_KEY (and optional VOYAGE_API_KEY)
python scripts/build_index.py   # one-time offline indexing
streamlit run frontend/app.py            # launch the demo front-end
```

## Example question

> "What are the primary risk factors facing Apple, Tesla, and JPMorgan, and how do they compare?"

More runnable examples live in `evals/` (each case has a `prompt.md`).

## Secrets

API keys come from `.env` (git-ignored) — never hardcode or commit them.

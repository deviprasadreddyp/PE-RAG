# agents.md — The-RAG Harness

> **Read this file first, every time.** It is the context for building anything in this repo.
> Do not rely on chat history from previous sessions — start a new chat and load this file.
> The whole point of this harness is to remove your freedom to invent conventions. Follow it.

---

## 1. What this project is

**The-RAG** is a Retrieval-Augmented Generation system that answers **business questions about
SEC EDGAR filings** (10-K annual + 10-Q quarterly reports, 2022–2026, ~54 large-cap US tickers)
and returns a **well-structured, grounded, cited answer produced by a single LLM API call.**

The hard constraint of the assessment: **indexing and retrieval run beforehand; the final answer
must come from exactly ONE Claude API request.** Never split the answer across multiple LLM calls.

## 2. Architecture (one paragraph + diagram)

A one-time **ingestion pipeline** loads the `.txt` filings, strips the XBRL noise, splits them into
section-aware, table-preserving chunks tagged with fiscal metadata, embeds them, and upserts them
into a persistent vector store plus a BM25 index. At query time, the **retrieval pipeline** parses
the question for metadata filters (ticker/form/period), runs hybrid (dense + BM25) search with those
filters, reranks, and assembles a token-budgeted context block with citations. The **generation
step** injects that context into a single Claude call using the grounded, cite-or-refuse prompt
template and returns the answer + sources. A **Streamlit front-end** is the input field for the demo.

```
                         ┌──────────────── OFFLINE (scripts/build_index.py) ────────────────┐
 edgar_corpus/*.txt ──▶ loader ──▶ parser ──▶ chunker ──▶ embedder ──▶ vector store (Chroma)
      + manifest.json      │        (strip XBRL,   (section-aware,   (voyage-        + BM25 index
                           │         read header)   table-safe)       finance-2)
                           └────────── metadata: ticker, company, form, filing_date, period, cik, section, url
                         ┌──────────────── ONLINE (per question) ──────────────────────────┐
 question ─▶ query parse (filters) ─▶ hybrid retrieve (filtered) ─▶ rerank ─▶ assemble context
                                                                                     │
                                                              ┌──────────────────────┘
                                                              ▼
                                        ONE Claude call (grounded prompt) ─▶ answer + citations
                                                              │
                                                     Streamlit front-end (app.py)
```

## 3. How to discover how to build something

**When you need to build or change any part of the system, read the matching skill in `skills/`
BEFORE writing code.** Each skill is an opinionated, detailed instruction set with a bad example,
a good example, known failure modes, and an explicit "MUST NOT" list. The skills are the source of
truth for *how* things are done here. If a skill and your instinct disagree, the skill wins. If a
skill is missing or wrong, update the skill (and note it) — don't route around it.

## 4. Canonical tech stack (do not substitute without updating this file)

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | |
| Package root | `sec_rag/` | one module per pipeline stage |
| Secrets | `.env` + `python-dotenv` | `ANTHROPIC_API_KEY`, optional `VOYAGE_API_KEY`. Never hardcode. |
| Embeddings | Voyage `voyage-finance-2` (default) | local `BAAI/bge-small-en-v1.5` fallback, behind an `Embedder` protocol |
| Vector store | **Chroma** (`PersistentClient`, `data/chroma/`) | native metadata `where` filtering; behind a `VectorStore` protocol |
| Sparse | `rank_bm25` | fused with dense via Reciprocal Rank Fusion (RRF) |
| Generation | **Claude** — `claude-opus-4-8` (final answer) | one `client.messages.create()`. Cheaper stages may use `claude-sonnet-5`/`claude-haiku-4-5`. Read `skills/single-call-rag.md`. |
| Front-end | **Streamlit** (`app.py`) | question input, answer, sources, retrieved chunks, latency/cost |
| Tests | `pytest` | |

> Before writing any Claude API call, consult the installed **`claude-api`** skill for model IDs,
> params, single-call patterns, structured output, and prompt caching — do not code from memory.

## 5. Repo / folder structure

```
The-RAG/
├── agents.md                     ← this file (the harness entry point)
├── DESIGN_DOC.md                 ← what the harness is + how to use it
├── templates/                    ← the feature workflow (see §6)
├── skills/                       ← how-to instructions, one per capability (see §7)
├── evals/                        ← proof the harness works (see §8)
├── features/active/<name>/       ← a feature in progress (instantiated templates)
├── edgar_corpus/                 ← the dataset (.txt filings + manifest.json) — READ-ONLY
├── sec_rag/                      ← application code
│   ├── config.py                 ← settings, model IDs, paths (all from env)
│   ├── ingest/                   ← loader.py, parser.py, chunker.py
│   ├── index/                    ← embedder.py, store.py
│   ├── retrieval/                ← retriever.py, context.py
│   ├── generation/               ← prompt.py (versioned), answer.py (the single call)
│   └── eval/                     ← run_eval.py, metrics
├── scripts/build_index.py        ← offline indexing entry point
├── data/                         ← chroma/, embedding cache — git-ignored
├── prompts/CHANGELOG.md          ← the prompt iteration log (required deliverable)
└── app.py                        ← Streamlit front-end
```

## 6. How to build a new feature (the workflow)

**Every new feature follows the sequence in `templates/`.** Do not skip to code.

1. Create `features/active/<feature-name>/`.
2. Copy the three templates into it and fill them out **in order**:
   - `01-product-spec.md` → who/what/why + success criteria
   - `02-technical-spec.md` → architecture, components, data models, interfaces
   - `03-implementation-plan.md` → ordered, testable build steps (data → index → retrieval → API → UI)
3. Read the skills the plan references.
4. Tell the coding tool: **"Build the implementation plan in `features/active/<name>/`."**
5. Build phase by phase; each phase is independently testable and committable.
6. When a phase changes the prompt, append an entry to `prompts/CHANGELOG.md`.

## 7. Glossary of skills (`skills/`)

| Skill | One-liner |
|---|---|
| `document-ingestion` | Load `.txt` filings + manifest, read the metadata header, strip the XBRL noise blob. |
| `chunking-strategy` | Section-aware, table-preserving chunking of 10-K/10-Q with fiscal metadata on every chunk. |
| `metadata-schema` | The exact metadata every chunk carries and how query filters map to it. |
| `embedding-generation` | Which embedding model, batching, content-hash caching, query vs document consistency. |
| `hybrid-retrieval` | Dense + BM25 fused with RRF, metadata pre-filtering, reranking, `k` selection. |
| `context-assembly` | Turn retrieved chunks into a token-budgeted, deduped, citation-tagged context block. |
| `single-call-rag` | The one-and-only Claude call: how to inject context and honor the single-call rule. |
| `prompt-template` | The grounded, cite-or-refuse prompt, its versioning, and the iteration log. |
| `answer-grounding` | Hallucination control, numeric fidelity, refusal on no-answer, citation format. |
| `frontend-streamlit` | The demo front-end: input, answer, sources, retrieved chunks, latency/cost. |
| `evaluation` | How retrieval and answer quality are measured (recall@k, MRR, faithfulness, refusal). |

## 8. Evals

`evals/` proves the harness works: rebuild an existing feature from scratch with only this harness
loaded and compare to the hand-built version. See `evals/README.md`. If fewer than 2 of the eval
cases pass, the harness is not ready — sharpen the failing skill and re-run.

## 9. Non-negotiable rules (NEVER violate)

1. **Single LLM call for the answer.** The final answer comes from exactly one Claude API request.
   Indexing, embedding, query parsing, and reranking may use other calls or models beforehand.
2. **Never fabricate financial data.** Do not invent numbers, tickers, dates, or filings to make
   code, tests, or a demo "work." Numbers come from the corpus, verbatim, with units and period.
3. **Cite or refuse.** Every answer cites its sources (ticker + form + period + section). If the
   context does not support an answer, the system says so — it never guesses.
4. **Never hardcode credentials.** API keys come from env / `.env` (git-ignored). No keys in code,
   logs, commits, or the front-end.
5. **Never embed or index the XBRL tag blob.** Strip it first (see `skills/document-ingestion`).
6. **Retrieval-scoped metadata is mandatory.** Every chunk carries the full metadata schema; never
   ship a chunk with no ticker/form/period.
7. **No silent truncation.** If context exceeds the budget, drop lowest-ranked chunks explicitly and
   record it — never cut the top chunk mid-table or drop numbers silently.
8. **Determinism where it matters.** Same corpus + same query ⇒ same retrieval. No wall-clock or
   randomness in the retrieval path.

## 10. Repo-specific architectural rules

- **Every chunk passes through the parser's XBRL-stripper and metadata extractor** before embedding.
  No chunk enters the index without the full metadata schema (`skills/metadata-schema`).
- **Every retrieval passes through the metadata filter stage** before vector search when the query
  names a company/form/period. Filter first, then rank — never rank over the whole corpus and hope.
- **Every answer passes through the grounding contract**: context injected → single call → answer
  carries inline citations → unsupported ⇒ refusal. `answer.py` returns `{answer, sources, usage}`.
- **The prompt is versioned.** `sec_rag/generation/prompt.py` holds the current template; every
  change is logged in `prompts/CHANGELOG.md` with what changed and why.
- **Ingestion is idempotent.** Re-running `build_index.py` on the same corpus does not duplicate
  chunks (upsert by stable chunk ID); the embedding cache is keyed by content hash.
- **Modules depend on abstractions.** Retrieval depends on `VectorStore`/`Embedder` protocols, not
  on Chroma/Voyage directly, so either can be swapped without touching business logic.

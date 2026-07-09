# agents.md — PE-RAG Harness

> **Read this file first, every time.** It is the context for building anything in this repo.
> Start a new chat and load this file; do not rely on prior chat history.
> The point of this harness is to remove your freedom to improvise. Follow it.

---

## 1. What this project is

**PE-RAG** is an **observable ingestion & retrieval pipeline** that answers a private-equity
analyst's natural-language question over **SEC EDGAR filings** (10-K + 10-Q) and returns a
**structured, grounded, cited answer from a single Claude API call.**

We are **not** "building a RAG." We are building an **observable pipeline**: every stage persists an
inspectable artifact, processing is deterministic except for the one generation call, and the whole
system is traceable end to end. The evaluator is judging the **engineering process**, not whether an
answer appears. Design doc: [`architecture/HLD.md`](architecture/HLD.md).

## 2. Engineering principles (apply everywhere)

1. **Simplicity over complexity** — the simplest design that solves it reliably.
2. **Deterministic wherever possible** — cleaning, metadata, section detection, chunking, retrieval,
   and citations use plain code. **LLMs are reserved for the final answer only.**
3. **Every stage is observable** — every offline stage writes its output to `data/<stage>/`. Nothing
   is a black box; you can inspect what each stage produced.
4. **Dataset-driven** — adapt to how SEC filings actually look, not to generic RAG defaults.

## 3. Architecture (pipeline + diagram)

A one-time **offline pipeline** turns filings into a searchable index, persisting an artifact at
every stage. At query time, a deterministic **retrieval pipeline** finds the right chunks; a single
**Claude call** turns them into a grounded, cited answer. Every query is logged.

```
OFFLINE (scripts/, one artifact per stage):
 edgar_corpus/*.txt
   → ingest    → data/raw/           (validated, unmodified)
   → clean     → data/cleaned/       (strip XBRL/whitespace/artifacts; keep business text + tables)
   → metadata  → data/metadata/      (deterministic: filename + manifest + header)
   → sections  → data/sections/      ({section_name, start, end})
   → chunk     → data/chunks/        (recursive split WITHIN sections; {chunk_id, section, text})
   → enrich    → (prepend Company/Filing/Year/Section to each chunk)
   → embed     → data/embeddings/    ({chunk_id, embedding, metadata})
   → store     → data/vectorstore/   (Chroma: vector + text + full metadata) + BM25 index

ONLINE (per question — no LLM until the last step):
 question → parse metadata filters (deterministic) → hybrid retrieve (vector + BM25 → RRF → top-k)
          → context builder → prompt builder → ONE Claude call → grounded answer + citations
                                                              → data/logs/ (per-query log)
```

## 4. Canonical tech stack (do not substitute without updating this file)

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | |
| Pipeline code | `src/` — one module per stage | mirrors the `data/<stage>/` folders 1:1 |
| Front-end | `frontend/app.py` (**Streamlit**) | normal mode + developer debug mode |
| Secrets | `.env` + `python-dotenv` | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` (embeddings). Never hardcode. |
| Embeddings | **OpenAI `text-embedding-3-large`** (default) | behind an `Embedder` protocol; Voyage `voyage-finance-2` / local `bge-small` are documented swappable alternatives |
| Vector store | **Chroma** (`PersistentClient`, `data/vectorstore/`) | native metadata `where` filtering; behind a `VectorStore` protocol |
| Sparse | `rank_bm25` | fused with dense via Reciprocal Rank Fusion (RRF) |
| Generation | **Claude `claude-opus-4-8`** | one `client.messages.create()`. Read `skills/single-call-rag.md`. |
| Tests | `pytest` | |

> Before writing any Claude API call, consult the installed **`claude-api`** skill for model IDs,
> params, the single-call pattern, and prompt caching — don't code from memory.

## 5. Repo / folder structure

```
PE-RAG/
├── agents.md                 ← this file (harness entry point)
├── architecture/HLD.md       ← the high-level design (the "why")
├── DESIGN_DOC.md             ← what the harness is + how to use it
├── templates/                ← the feature workflow (§7)
├── skills/                   ← how-to instructions, one per capability/stage (§8)
├── evals/                    ← HARNESS self-tests (rebuild a feature, compare) (§9)
├── evaluation/               ← RAG QUALITY dataset + grounding notes (HLD §9) — different from evals/
├── prompt_iterations/        ← the prompt iteration log (required deliverable)
├── features/active/<name>/   ← a feature in progress (instantiated templates)
├── edgar_corpus/             ← dataset (.txt git-ignored; manifest.json tracked) — READ-ONLY
├── src/                      ← pipeline code, one module per stage
│   ├── config.py             ← settings, model IDs, paths (all from env)
│   ├── observability.py      ← persist_artifact() / load_artifact() helpers used by every stage
│   ├── query_log.py          ← per-query logging
│   ├── pipeline/             ← ingest.py, clean.py, metadata.py, sections.py, chunk.py, enrich.py, embed.py, store.py
│   ├── retrieval/            ← parse.py (filters), search.py (hybrid+RRF), context.py
│   └── generation/           ← prompt.py (versioned), generate.py (the single call)
├── scripts/                  ← run_ingest.py … build_index.py (offline, stage by stage)
├── data/                     ← raw/ cleaned/ metadata/ sections/ chunks/ embeddings/ vectorstore/ logs/  (git-ignored)
└── frontend/app.py           ← Streamlit UI
```

## 6. How to build a new feature (the workflow)

Every feature follows `templates/`. Do not skip to code.
1. Create `features/active/<feature-name>/`.
2. Fill the three templates **in order**: `01-product-spec` → `02-technical-spec` → `03-implementation-plan`.
3. Read the skills the plan references.
4. Tell the tool: **"Build the implementation plan in `features/active/<name>/`."**
5. Build stage by stage; each stage persists its artifact and is independently testable/committable.
6. Any prompt change → append an entry to `prompt_iterations/CHANGELOG.md`.

## 7. Glossary of skills (`skills/`)

| Skill | One-liner |
|---|---|
| `observability` | The core pattern: every stage persists an inspectable artifact to `data/<stage>/`. |
| `document-ingestion` | Load `.txt` + manifest, validate, read the metadata header, store raw. |
| `document-cleaning` | Strip XBRL/whitespace/artifacts; preserve business text, section titles, tables. |
| `metadata-schema` | The exact per-chunk metadata + deterministic query→filter mapping (never an LLM). |
| `section-detection` | Detect SEC sections (Risk Factors, MD&A, …) with offsets, deterministically. |
| `chunking-strategy` | Recursive split WITHIN sections; table-preserving; stable chunk IDs. |
| `chunk-enrichment` | Prepend Company/Filing/Year/Section to each chunk before embedding. |
| `embedding-generation` | OpenAI `text-embedding-3-large`, batched, content-hash cached, query/doc consistent. |
| `hybrid-retrieval` | Metadata pre-filter → dense + BM25 → RRF → top-k. Deterministic. |
| `context-assembly` | Token-budgeted, deduped, citation-tagged context block; no silent truncation. |
| `single-call-rag` | The one-and-only Claude call: inject context, honor the single-call rule. |
| `prompt-template` | The grounded, cite-or-refuse prompt, its versioning, and the iteration log. |
| `answer-grounding` | Hallucination control, numeric fidelity, refusal on no-answer, citation format. |
| `frontend-streamlit` | Streamlit UI: answer + citations, plus a developer debug panel over the pipeline. |

Per-query logging (rule #10) is implemented as code in `src/query_log.py`, not as a skill.
| `evaluation` | Retrieval + answer quality metrics + the `evaluation/` dataset (recall@k, faithfulness…). |

## 8. Evals

`evals/` proves the **harness** works (rebuild a feature with only the harness loaded, compare to
expected). `evaluation/` holds the **RAG quality** dataset. See `evals/README.md`. If fewer than 2 of
the harness cases pass, the harness is not ready — sharpen the failing skill and re-run.

## 9. Non-negotiable rules (NEVER violate)

1. **Single Claude call for the answer.** The final answer comes from exactly one Claude API request.
   Everything else (ingest, clean, metadata, sections, chunk, embed, retrieve, rerank) runs before it.
2. **Every offline stage persists an inspectable artifact** to `data/<stage>/` (observability). No
   stage is a black box; intermediate outputs are always written and re-loadable.
3. **Deterministic except generation.** Do NOT use an LLM for cleaning, metadata extraction, section
   detection, chunking, retrieval, or citation construction — plain code only.
4. **Never fabricate financial data.** No invented numbers, tickers, dates, or filings. Numbers come
   from the corpus, verbatim, with units and fiscal period.
5. **Cite or refuse.** Every answer cites sources (ticker + form + period + section). If the context
   doesn't support an answer, say so — never guess.
6. **Never hardcode credentials.** Keys come from env / `.env` (git-ignored). Never in code/logs/UI.
7. **Never embed or index the XBRL blob.** Strip it in the cleaning stage.
8. **Full metadata schema on every chunk** (`skills/metadata-schema`). No chunk without ticker/form/period.
9. **No silent truncation.** Over budget ⇒ drop lowest-ranked chunks explicitly and record it; never
   cut the top chunk mid-table or drop numbers.
10. **Every query is logged** to `data/logs/`: question, retrieved chunk IDs, similarity scores,
    prompt, response, latency, tokens, cost, timestamp.

## 10. Repo-specific architectural rules

- **Every stage reads the previous stage's artifact and writes its own** via `src/observability.py`
  (`persist_artifact` / `load_artifact`). Stages are runnable and inspectable in isolation.
- **Cleaning strips the XBRL blob; chunking splits within sections; enrichment prepends context** —
  in that order — before embedding. No chunk enters the index without the full metadata schema.
- **Every retrieval passes through the deterministic metadata filter** before vector search when the
  query names a company/form/period. Filter first, then rank.
- **Every answer passes through the grounding contract**: context injected → single call → inline
  citations → unsupported ⇒ refusal. `generate.py` returns `{answer, sources, retrieved, usage}`.
- **The prompt is versioned** in `src/generation/prompt.py`; every change is logged in
  `prompt_iterations/CHANGELOG.md` (what changed + why + eval effect).
- **Ingestion/indexing is idempotent** — re-runs upsert by stable chunk ID; embeddings cached by
  content hash.
- **Modules depend on abstractions** — retrieval depends on `VectorStore`/`Embedder` protocols, not
  on Chroma/OpenAI directly, so either can be swapped without touching business logic.
- **Debug mode over the same artifacts** — the front-end's debug panel reads the persisted artifacts
  and the per-query log, so what you inspect is exactly what ran.

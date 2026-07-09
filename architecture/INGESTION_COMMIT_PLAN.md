# Ingestion Pipeline — Commit Plan

**Total: 16 commits** for the full offline ingestion & indexing pipeline (HLD Stages 1–8) plus
scaffolding, orchestration, and inspection. Deterministic code only — **no LLM anywhere in this
phase** (the single Claude call belongs to Phase 2). Each commit is small, independently testable,
and auto-pushed by the post-commit hook.

**Stack:** Python 3.11 · LangChain (`RecursiveCharacterTextSplitter`, `OpenAIEmbeddings`, `Chroma`,
BM25) · `chromadb` · `openai` · `pydantic-settings` · `pytest`. FastAPI enters in Phase 2 (serving).

**Conventions applied to every commit (don't repeat in each prompt):**
- Follow `agents.md` and `architecture/HLD.md`.
- Every stage reads the previous stage's artifact and persists its own to `data/<stage>/` via
  `src/observability.py`. Nothing is a black box.
- Deterministic: no LLM, no wall-clock/random in artifact bodies; same input ⇒ same output.
- Add `pytest` tests for each stage. Keep functions pure where practical.
- Conventional-commit message (given per commit); the hook pushes automatically.

---

## Phase 1a — Scaffolding & foundations (commits 1–5)

### Commit 1 — `chore: pipeline scaffolding (deps, package, data dirs)`
**Prompt:** "Set up the project skeleton for the ingestion pipeline. Create `requirements.txt` (or
`pyproject.toml`) pinning: `langchain`, `langchain-openai`, `langchain-community`, `langchain-chroma`,
`chromadb`, `openai`, `rank-bm25`, `pydantic-settings`, `python-dotenv`, `fastapi`, `uvicorn`,
`streamlit`, `pytest`. Create the `src/` package (`src/__init__.py`, `src/pipeline/__init__.py`,
`src/retrieval/__init__.py`, `src/generation/__init__.py`) and `tests/`. Create the `data/`
subfolders (`raw cleaned metadata sections chunks embeddings vectorstore logs`) each with a
`.gitkeep`. Add `OPENAI_API_KEY` to `.env.example`. No logic yet."
**Does:** dependency manifest, empty package tree, `data/<stage>/` dirs (git-tracked via `.gitkeep`,
contents ignored), updated `.env.example`. Verify: `pip install -r requirements.txt` succeeds.

### Commit 2 — `feat(config): typed settings from env`
**Prompt:** "Create `src/config.py` using `pydantic-settings.BaseSettings`. Load from `.env`:
`openai_api_key`, `anthropic_api_key`, `embedding_model='text-embedding-3-large'`,
`generation_model='claude-opus-4-8'`, `chunk_size`, `chunk_overlap`, and `data_dir='data'`,
`corpus_dir='edgar_corpus'`, `chroma_dir='data/vectorstore'`, `collection_name`. Expose a singleton
`settings`. Never hardcode secrets. Add a test that settings load from a sample env mapping."
**Does:** one typed config object every module imports; keys come from env only. Test: overrides via
env are respected; defaults present.

### Commit 3 — `feat(schemas): pydantic models for pipeline artifacts`
**Prompt:** "Create `src/schemas.py` with pydantic models: `DocMetadata` (company, ticker, form,
filing_date, report_period, fiscal_period, year, quarter, cik, source_url, source_file),
`SectionSpan` (section_name, item, start, end), `Chunk` (id, doc_id, text, embed_text, section,
chunk_index + all DocMetadata fields), `RetrievalResult` (chunk, score), `Answer` (answer, sources,
retrieved, usage). Chroma-safe types only (str/int/float/bool; use '' not None). Add tests
constructing each and asserting JSON round-trips."
**Does:** the contracts every stage passes around; single source of truth for the chunk schema.

### Commit 4 — `feat(observability): stage artifact persistence helpers`
**Prompt:** "Create `src/observability.py` with `persist_artifact(stage, doc_id, obj, ext='json')`
and `load_artifact(stage, doc_id, ext='json')` writing under `data/<stage>/<doc_id>.<ext>` (JSON
pretty-printed, `indent=2, ensure_ascii=False`; txt written raw). Add `list_artifacts(stage)` and
`stage_count(stage)`. Deterministic, no timestamps in bodies. Add tests for round-trip (json + txt),
directory creation, and overwrite idempotency."
**Does:** the backbone of the observable pipeline — every later stage uses these. Test: write→read
equality; re-write overwrites without duplicating.

### Commit 5 — `chore(spike): corpus inspection to set chunking params`
**Prompt:** "Create `scripts/inspect_corpus.py` that scans `edgar_corpus/` (via `manifest.json`) and
reports: file count and size distribution, header field coverage (which files have Report
Period/Quarter), where the XBRL blob ends / prose begins, and section-heading patterns per form. Print
a summary and write it to `architecture/corpus_notes.md`. Use the findings to set `chunk_size` and
`chunk_overlap` defaults in `src/config.py` and record the rationale (dataset-driven decision). No
persistence to `data/`."
**Does:** grounds chunk size/overlap and section regexes in the real corpus rather than defaults.
Verify: `corpus_notes.md` written; config defaults updated with a comment citing it.

---

## Phase 1b — Ingestion stages (commits 6–13, one per HLD stage)

### Commit 6 — `feat(ingest): stage 1 raw ingestion + validation`
**Prompt:** "Implement Stage 1 in `src/pipeline/ingest.py`. Read `edgar_corpus/manifest.json` (the
authoritative file list). For each file: validate existence, UTF-8 decodability, and filename pattern
`TICKER_FORM_[PERIOD]_YYYY-MM-DD_full.txt`; on failure append `(filename, reason)` to a dead-letter
list. Do NOT modify content. Persist each raw file unchanged to `data/raw/<doc_id>.txt`
(`doc_id` = filename without `_full.txt`) via `persist_artifact`. Write dead-letters to
`data/raw/_dead_letter.json`. Tests: manifest parse, valid/invalid filename, raw artifact is
byte-identical to source. Do NOT strip XBRL here."
**Does:** `data/raw/` populated, unmodified, with a dead-letter record. First inspectable artifact.

### Commit 7 — `feat(clean): stage 2 cleaning (strip XBRL, keep business text)`
**Prompt:** "Implement Stage 2 in `src/pipeline/clean.py`. Load `data/raw/<doc_id>.txt`. Split off the
`====` header. Strip the leading XBRL/us-gaap blob by anchoring on the first prose marker
(`UNITED STATES`/`SECURITIES AND EXCHANGE COMMISSION`/`FORM 10-[KQ]`); drop residual tag lines and
collapse blank runs. PRESERVE business text, section titles, numbers/units, and table rows. Persist
to `data/cleaned/<doc_id>.txt`. Tests: no `us-gaap:` markers remain; a known revenue figure and a
section title survive; cleaned length < raw length but > 50% of body. Deterministic; no LLM."
**Does:** `data/cleaned/` — noise-free, business-preserving text. Raw↔cleaned diff is inspectable.

### Commit 8 — `feat(metadata): stage 3 deterministic metadata extraction`
**Prompt:** "Implement Stage 3 in `src/pipeline/metadata.py`. Build `DocMetadata` deterministically
from the header block + filename + manifest (NEVER an LLM). Parse header lines (Company, Ticker,
Filing Type, Filing Date, Report Period, Quarter, CIK, URL); backfill `fiscal_period`/`year`/`quarter`
from the filename when the header lacks them; normalize `form` to exactly `10-K`/`10-Q`. Persist to
`data/metadata/<doc_id>.json`. Tests: header-over-filename precedence, a file missing the period line,
form normalization."
**Does:** `data/metadata/` — the fields that power retrieval filters and citations.

### Commit 9 — `feat(sections): stage 4 section detection with offsets`
**Prompt:** "Implement Stage 4 in `src/pipeline/sections.py`. On `data/cleaned/<doc_id>.txt`, detect
SEC items via anchored regex (`^\\s*Item\\s+\\d+[A-Z]?\\.`), taking the LAST occurrence of each heading
(skip the table of contents). Record `SectionSpan{section_name, item, start, end}` char offsets;
map item numbers to human names (1A→Risk Factors, 7→MD&A, 8→Financial Statements, …); bucket text
outside any section as 'Other' rather than dropping it. Persist to `data/sections/<doc_id>.json`.
Tests: TOC entry not matched, offsets contiguous and cover the whole doc, missing item handled."
**Does:** `data/sections/` — section boundaries so chunking never crosses unrelated sections.

### Commit 10 — `feat(chunk): stage 5 chunk generation within sections`
**Prompt:** "Implement Stage 5 in `src/pipeline/chunk.py`. For each section span, slice the cleaned
text and split it with LangChain `RecursiveCharacterTextSplitter` (`chunk_size`/`chunk_overlap` from
config; separators favouring paragraph→line→sentence). Never split across sections. Emit `Chunk`
objects with a stable `id` (`{doc_id}_{chunk_index}`), `section`, `text`, `chunk_index`, and all
metadata. Persist to `data/chunks/<doc_id>.json`. Tests: no chunk spans two sections, ids are stable
across re-runs, every chunk carries full metadata, chunk sizes within bounds."
**Does:** `data/chunks/` — section-scoped, metadata-complete chunks. Deterministic (fixed splitter).

### Commit 11 — `feat(enrich): stage 6 chunk enrichment (embed_text)`
**Prompt:** "Implement Stage 6 in `src/pipeline/enrich.py`. For each chunk in `data/chunks/<doc_id>.json`,
set `embed_text = 'Company: {company} | Filing: {form} | Year: {year} | Section: {section}\\n---\\n' +
text`, leaving the original `text` untouched (display/citation). Re-persist to `data/chunks/`. Tests:
`text` unchanged, `embed_text` starts with the header, header format identical across chunks."
**Does:** enriched `embed_text` for better embeddings; original text preserved for citations.

### Commit 12 — `feat(embed): stage 7 embeddings (OpenAI, batched, cached)`
**Prompt:** "Implement Stage 7 in `src/pipeline/embed.py` using LangChain
`OpenAIEmbeddings(model='text-embedding-3-large')`. Embed each chunk's `embed_text` in batches; cache
each vector by `sha256(model + embed_text)` under `data/.embedding_cache/` so re-runs don't re-embed.
Persist `{chunk_id, embedding, metadata}` per doc to `data/embeddings/<doc_id>.json`. Read the key from
config (env). Tests MOCK the embeddings client (no network): assert batching, cache hit on second
call, and that `embed_text` (not `text`) is embedded."
**Does:** `data/embeddings/` — vectors + metadata, with a content-hash cache for idempotent re-runs.

### Commit 13 — `feat(store): stage 8 Chroma upsert + BM25 index`
**Prompt:** "Implement Stage 8 in `src/pipeline/store.py`. Build a persistent LangChain `Chroma`
(`persist_directory=data/vectorstore`, collection from config incl. embedding model). Upsert all
chunks with `ids=chunk_id`, `documents=text` (original), `embeddings` (from Stage 7), and full
`metadatas` (ticker/company/form/fiscal_period/section/source_url/…). Also build a BM25 index over the
same chunk texts (`rank_bm25` or LangChain `BM25Retriever`) and persist its state (tokenized corpus +
ids) under `data/vectorstore/bm25.json`. Wrap Chroma behind a `VectorStore` protocol. Tests: upsert
count equals chunk count, a metadata `where` query returns the right ticker, re-run is idempotent
(no duplicate ids), BM25 loads and returns hits."
**Does:** `data/vectorstore/` — the searchable dense + sparse index. End of the offline pipeline.

---

## Phase 1c — Orchestration & inspection (commits 14–16)

### Commit 14 — `feat(cli): pipeline orchestrator`
**Prompt:** "Create `src/run.py` (runnable as `python -m src.run`) with a CLI (argparse/Typer):
`--stage {ingest,clean,metadata,sections,chunk,enrich,embed,store,all}` and optional `--doc-id` to run
one filing. Running `all` executes stages in order for every doc, each reading the prior artifact and
writing its own. Idempotent and resumable (skips a stage whose artifact is current unless
`--force`). Also add `scripts/build_index.py` calling `run(stage='all')`. Tests: `all` on a 2-file
fixture produces every `data/<stage>/` artifact; re-run is a no-op without `--force`."
**Does:** one command builds the whole index; any single stage runs in isolation for debugging.

### Commit 15 — `feat(inspect): stage inspection report`
**Prompt:** "Create `src/inspect.py` (`python -m src.inspect`) that prints, per stage: artifact count,
a truncated sample artifact, and sanity checks — no `us-gaap:` markers in `data/cleaned/`, every chunk
has full metadata + non-empty `embed_text`, every section span has valid offsets, embeddings count ==
chunk count, Chroma collection size == chunk count. Exit non-zero if any check fails. This is the
observability payoff and the demo's 'inspect any stage' story."
**Does:** a one-command health view of the whole pipeline; catches 'cleaning removed too much',
'chunk missing metadata', 'embeddings out of sync' immediately.

### Commit 16 — `docs: ingestion README + architecture + assumptions`
**Prompt:** "Update `README.md` with an Ingestion section: how to install, set `.env`, run
`python -m src.run --stage all`, and inspect `data/<stage>/` + `python -m src.inspect`. Add an
architecture diagram (reference `architecture/HLD.md`) and an Assumptions list (chunk size rationale
from the spike, header-over-filename metadata rule, XBRL-strip boundary, deterministic-except-LLM).
No code changes."
**Does:** the ingestion pipeline is documented, runnable, and inspectable by anyone cloning the repo.

---

## After this (Phase 2 — separate ~12-commit plan, on request)
Retrieval (`parse` filters → hybrid `search` + RRF → `context` builder) · **FastAPI** `/query` endpoint
· the **single Claude call** (`generation/prompt.py` + `generate.py`) · per-query logging
(`src/query_log.py`) · **Streamlit** front-end with normal + debug mode · the `evaluation/` dataset and
metrics. Ask and I'll detail Phase 2 the same way.

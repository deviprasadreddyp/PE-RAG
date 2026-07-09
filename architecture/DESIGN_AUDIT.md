# Design Audit — target design vs. current implementation

Audit of the current codebase (commits through `docs: ingestion README`) against the refined design
(controlled normalization; Normalization vs Structural Parsing split; 10-stage pipeline).

**Status legend:** ✅ implemented & matches · ⚠️ partial · ↔️ divergent (built differently) ·
❌ not implemented. **Decision column is "defer" everywhere — no changes made from this audit.**

## Headline
> **Update (current):** Parts A–C below are the *original* audit (kept for the record). Bucket **A**
> (cleaning philosophy) and **all** of Bucket **B** (items 2–11) have since been implemented and
> re-run — see **Part D** at the bottom. The only remaining gaps are **Phase 2** and the **real
> embed/store runs**. 98 tests pass.

- The **offline pipeline (Stages 1–8) is built, tested, observable, and documented**, now on the
  **controlled-normalization** design with typed records, incremental indexing, canonical sections +
  Part tree, and semantic-hierarchical max-cap chunking.
- The remaining gaps are **all of Phase 2** (retrieval, fusion, single LLM call, debug UI) and the
  **real embed/store runs** (need `sentence-transformers` + compute; embeddings are local, no key).

---

## Ingestion (Stages 0–9)

| Item (your design) | Current implementation | Status | Documented? | Decision |
|---|---|---|---|---|
| **Stage 0 — Corpus discovery** as its own step | Folded into Stage 1 (ingest) | ↔️ | partly | defer |
| &nbsp;• deterministic document UUID | We use a deterministic filename-derived `doc_id` (not a UUID) | ↔️ | yes | defer |
| &nbsp;• SHA-256 per doc (incremental indexing) | **Not done** (sha256 is used only for the *embedding* cache) | ❌ | no | defer |
| &nbsp;• `data/raw_index.json` (DocumentRecord: size, created_at, status, absolute_path) | **Not done** (only `data/raw/_dead_letter.json`) | ❌ | no | defer |
| &nbsp;• `created_at` timestamp | **Deliberately omitted** (determinism principle — no timestamps in artifacts) | ↔️ | yes | defer |
| **Stage 1 — Raw preservation** (byte-faithful copy) | ✅ `data/raw/` byte-faithful, validated, dead-lettered | ✅ | yes | keep |
| **Stage 2 — Controlled Normalization** (cosmetic, reversible) | Current is **aggressive**: cuts the whole leading XBRL blob (anchor on `FORM 10-K`) + drops tag lines | ↔️ **(the key change)** | yes (old design) | **defer — likely change** |
| &nbsp;• 2.1 encoding → UTF-8 | ✅ read/write utf-8; ingest validates decodability | ✅ | yes | keep |
| &nbsp;• 2.2 CRLF → LF | Implicit (read_text universal newlines) — not an explicit step | ⚠️ | no | defer |
| &nbsp;• 2.3 collapse excessive blank lines | ✅ `\n{3,}` → `\n\n` | ✅ | yes | keep |
| &nbsp;• 2.4 tabs→spaces, multi-space→single (except tables) | **Not done** — we keep all internal spacing to protect tables | ↔️ | partly | defer |
| &nbsp;• 2.5–2.7 remove *isolated* XBRL/XML/taxonomy lines only | We remove the whole leading blob + any `^\d{6,}(ns):` line — broader than "isolated only" | ↔️ | yes | **defer — likely change** |
| &nbsp;• 2.8 preserve tables/numbers/lists/headings | ✅ preserved (verified: figures/tables survive) | ✅ | yes | keep |
| **Normalization vs Structural Parsing split** | Not a hard split — `clean.py` mixes cosmetic normalization with a structural anchor-cut; metadata/sections are already separate stages | ↔️ | no | **defer — likely change** |
| **Stage 3 — Metadata (deterministic)** | ✅ header + filename, header wins, no LLM | ✅ | yes | keep |
| &nbsp;• field names | We use `form` (not `filing_type`); no `document_id`, no `source:"SEC"` field | ↔️ | yes | defer |
| &nbsp;• `industry` field | **Not extracted** (not in header/filename; manifest has only a corpus-level sector blurb) | ❌ | no | defer |
| &nbsp;• company/CIK from **manifest** | We take company/CIK from the **header** (manifest has no per-file company/CIK) | ↔️ | yes | defer |
| **Stage 4 — Hierarchical section detection** | ✅ inline `Item N.` (nbsp + pipe), offsets, 226/246 (92%), graceful "Other" | ✅ | yes | keep |
| **Stage 5 — Section-aware recursive chunking** | ✅ within-section recursive split, parent/child indices | ✅ | yes | keep |
| &nbsp;• size ~1000 **tokens** / 150 overlap | We use **3000 chars / 300 overlap** (~750 tokens), char-based (no tiktoken) — dataset-driven | ↔️ | yes | defer |
| **Stage 6 — Chunk enrichment** | ✅ `embed_text` header + text, idempotent | ✅ | yes | keep |
| &nbsp;• header fields Company/Ticker/Form/Year/Quarter/Section | We include Company/Filing/Year/Section — **missing Ticker & Quarter** | ⚠️ | yes | defer |
| **Stage 7 — Embedding** (OpenAI text-embedding-3-large) | ✅ built, batched, content-hash cached — **real run deferred** (needs key, ~32K chunks) | ✅ (code) | yes | keep / run later |
| **Stage 8 — Vector store (Chroma)** | ✅ persistent, idempotent upsert, metadata — **real build deferred** (needs embeddings) | ✅ (code) | yes | keep / run later |
| &nbsp;• collection name `sec_filings` | We use `sec_filings__text-embedding-3-large` (model-namespaced) | ↔️ | yes | defer |
| **Stage 9 — BM25 (separate index)** | ✅ built inside `store.py` (`data/vectorstore/bm25.json`) | ✅ | yes | keep |

---

## Retrieval & serving (Stage 10+ — Phase 2, not yet built)

| Item | Current | Status | Documented? | Decision |
|---|---|---|---|---|
| Stage 10 retrieval pipeline | Not built | ❌ | yes (plan/README) | defer |
| Deterministic metadata parsing (question → company/year/quarter/form filters) | Not built | ❌ | yes (skills) | defer |
| Hybrid fusion (Reciprocal Rank Fusion) | Not built (BM25 + Chroma exist; fusion not wired) | ❌ | yes | defer |
| Deduplication | Not built | ❌ | yes | defer |
| Prompt builder + **single Claude call** (cite-or-refuse, "Information unavailable") | Not built | ❌ | yes | defer |
| Per-query logging (`data/logs/`) | Folder exists; no logger yet | ❌ | yes | defer |
| Debug UI (metadata filters → retrieved → similarity → fusion → prompt → response → sources) | Not built | ❌ | yes (skill/HLD) | defer |
| Observability folders `retrieval/ prompt/ responses/` | We have `raw cleaned metadata sections chunks embeddings vectorstore logs` (no retrieval/prompt/responses) | ⚠️ | partly | defer |

---

## What is solid (keep)
- Stages 1–8 implemented, **82 passing tests**, every stage persists an inspectable artifact.
- Deterministic everywhere; **no LLM** in ingestion. Idempotent re-runs; embedding content-hash cache.
- Section-Aware Hierarchical Chunking matches the target design (parent sections → child chunks).
- Orchestrator (`src/run.py`) + inspection report (`src/inspect.py`) + corpus spike.
- Docs: `README.md`, `architecture/HLD.md`, `CHUNKING_STRATEGY.md`, `corpus_notes.md`,
  `INGESTION_COMMIT_PLAN.md`.

## Decisions to make later (nothing changed yet)
1. **Cleaning philosophy** — switch Stage 2 from aggressive blob-cut to **controlled normalization**,
   and split into **Normalization** (cosmetic/reversible) + **Structural Parsing** (headings/sections).
   *This is the main one.*
2. **Stage 0 discovery artifact** — add `data/raw_index.json` with sha256 (+ maybe UUID) for
   incremental indexing; reconcile `created_at` with the no-timestamp determinism rule.
3. **Normalization sub-steps** — explicit CRLF→LF, tabs→spaces, multi-space collapse (table-safe).
4. **Metadata** — add `industry`/`source`/`document_id`? rename `form`→`filing_type`? (source of `industry`?)
5. **Chunk sizing** — keep 3000 chars/300, or move to ~1000 tokens/150 (add a token length function)?
6. **Enrichment header** — add Ticker & Quarter.
7. **Collection name** — `sec_filings` vs the model-namespaced name.
8. **Phase 2** — retrieval + fusion + dedup + single call + logging + debug UI (separate plan).

---

# Part B — 25-point CTO review

Cross-check of the 25-point critique against the code. **Legend:** ✅ done · ⚠️ partial ·
↔️ divergent · ❌ missing. **New?** 🆕 = a gap not already in Part A · ↺ = overlaps Part A.
All decisions **deferred** — no code changed.

| # | Item | Current state | Status | New? |
|---|------|---------------|--------|------|
| 1 | Document parsing strategy (explicit regex → normalize → **canonical names** → section tree) | Regex nbsp/pipe headings + cross-ref exclusion + title extraction; **no canonical-name map** (uses raw heading title), **no explicit section tree** (flat spans + parent/child indices) | ⚠️ | 🆕 |
| 2 | **Deterministic chunk IDs** (not random UUID) | ✅ deterministic `{doc_id}_{index}` — but **not** the section-encoded human form `AAPL_2024_10K_RiskFactors_Chunk_03` | ⚠️ | 🆕 |
| 3 | Incremental indexing via SHA-256 | ❌ no doc-level sha256 / change-detect (have mtime idempotency + embedding content-hash cache) | ❌ | ↺ (Part A #2) |
| 4 | Embedding batch size + retry/backoff | ⚠️ one batched call via LangChain/openai **defaults**; no explicit batch size or backoff | ⚠️ | 🆕 |
| 5 | Error handling every stage (one corrupt file ≠ stop 246) | ⚠️ **only ingest** dead-letters; clean/metadata/sections/chunk/embed **abort** on a bad doc (no per-doc try/except) | ⚠️ | 🆕 **(important)** |
| 6 | Configuration (`config.yaml`) | ↔️ configurable via **pydantic-settings + .env** (env vars), not a YAML file | ↔️ | 🆕 |
| 7 | Retrieval strategy (precise stages) | ❌ Phase 2 | ❌ | ↺ |
| 8 | Metadata filtering (**hard** filters vs **soft** semantic) | ❌ parsing not built (schema supports filters; distinction undocumented) | ❌ | 🆕 (the hard/soft framing) |
| 9 | BM25 implementation named | ✅ `rank_bm25` (BM25Okapi) | ✅ | — |
| 10 | Reciprocal Rank Fusion **with formula** (`Σ 1/(k+r)`) | ❌ not built; formula not documented | ❌ | 🆕 (formula) |
| 11 | Chroma record schema (id/embedding/document/metadata/**CreatedAt/Hash**) | ⚠️ store id + embedding + document + metadata; **no CreatedAt/Hash** on records | ⚠️ | 🆕 |
| 12 | Actual prompt template (system/rules/context/question/output) | ❌ Phase 2 (skill describes it; no concrete template) | ❌ | ↺ |
| 13 | **Structured output schema** (exec summary / comparison / evidence / citations / confidence) | ❌ Phase 2 (design implies markdown; structured schema unspecified) | ❌ | 🆕 |
| 14 | Exact citation format (`[Apple 10-K 2024] → Section → Chunk ID`) | ❌ Phase 2 (Citation model exists; exact render unspecified) | ❌ | 🆕 |
| 15 | Confidence score (avg similarity → high/med/low, no LLM) | ❌ not implemented | ❌ | 🆕 |
| 16 | Log separation (pipeline / app / query / evaluation) | ❌ `data/logs/` folder exists; **no logger** and no separation | ❌ | 🆕 |
| 17 | Evaluation metrics code (recall@k, precision@k, MRR; grounded/complete/citation-coverage) | ❌ no code / no `evaluation/` dataset (skill documents metrics only) | ❌ | 🆕 (as code) |
| 18 | Debug mode (exact stage trace) | ❌ Phase 2 | ❌ | ↺ |
| 19 | Data classes (Document / Section / Chunk / **EmbeddingRecord** / RetrievalResult / Response) | ⚠️ have Section/Chunk/RetrievalResult/Answer(=Response); **no typed `Document`**, embeddings are **plain dicts** not an `EmbeddingRecord` | ⚠️ | 🆕 |
| 20 | Project structure (per-concern folders: ingestion/normalization/metadata/…) | ↔️ flatter: `src/pipeline/` holds all ingest stages; `retrieval/`, `generation/` empty | ↔️ | 🆕 |
| 21 | Hybrid retrieval spec (metadata → BM25 top20 → vector top20 → RRF → dedup → top8) | ❌ Phase 2 | ❌ | ↺ |
| 22 | Retrieval context-builder stage | ❌ Phase 2 | ❌ | ↺ |
| 23 | OpenAI retry policy (429 → backoff → 3 attempts) | ⚠️ openai SDK default (max_retries=2) via LangChain; not explicit/tuned | ⚠️ | 🆕 (overlaps #4) |
| 24 | Cost tracking (tokens / embed cost / gen cost / latency) | ❌ only `Answer.usage` placeholder; no tracking code | ❌ | 🆕 |
| 25 | **Assumptions as a dedicated architecture section** | ⚠️ present in README + this audit + corpus_notes, but no dedicated `architecture/ASSUMPTIONS.md` | ⚠️ | 🆕 |

## Three-level architecture (Business / Logical / Physical)
❌ Not structured this way. `HLD.md` is roughly the **Logical** layer; there is no **Business
Architecture** (why each component exists) and no single **Physical Implementation Spec** (exact
classes, folders, config schema, algorithms/formulae, retry policies, storage schema, log/eval specs).
Much of Part B is really *documentation explicitness*, which a Physical Spec would resolve. 🆕

## Verdict & how to close the gaps
- Agree with ~**85%**: the ingestion **core** is solid and tested; what's thin is **spec explicitness**
  (formulae, templates, schemas, config file, error/retry/cost/log/eval policies, structured output)
  and **all of Phase 2**.
- Two kinds of gaps: **(a) documentation** — writeable now without code (items 1,8,10,11,13,14,16,20,25
  + the three-level doc); **(b) code** — either small hardening on the built pipeline
  (items 2,4,5,6,19,24 + sha256 #3) or Phase 2 (7,12,15,17,18,21,22,23).

## Deferred decisions (nothing changed — pick per item)
- **Harden the built pipeline?** per-stage error isolation (#5), explicit embedding batch/retry (#4/23),
  `config.yaml` vs env (#6), section-encoded chunk IDs (#2), typed `Document`/`EmbeddingRecord` (#19),
  canonical section names + tree (#1), doc-level sha256 (#3), cost tracking (#24), Chroma CreatedAt/Hash (#11).
- **Write the spec-explicitness docs?** RRF formula, prompt template, output/citation/confidence schema,
  hard-vs-soft filtering, log taxonomy, project-structure map, dedicated ASSUMPTIONS, three-level doc.
- **Build Phase 2?** retrieval → fusion → dedup → context builder → single call → logging → eval → debug UI.

---

# Part C — Category A: RESOLVED (this supersedes the "deferred" lists above for these items)

**Implemented (code + tests):**
- ✅ **#5 Per-stage error isolation** — `observability.run_docs` + orchestrator; one bad filing is
  dead-lettered to `data/logs/<stage>_failures.json`, never aborts the rest. (commit `9a1aa09`)
- ✅ **#4 / #23 Embedding batch size + retry/backoff** — `embed_batch_size=100`, `embed_max_retries=3`
  (exponential backoff on 429/5xx) wired into `OpenAIEmbedder`. (commit `34d9205`)
- ✅ **#2 Section-aware deterministic chunk IDs** — `{doc_id}__{Section}_c{NN}`, 32,050/32,050 unique
  on the real corpus. (commit `7f25d48`)

**Documented (explicit spec written — code where noted is Phase 2):**
- ✅ **#7/#21 Retrieval strategy + hybrid spec**, **#8 hard-vs-soft filtering**, **#10 RRF formula**
  (`Σ 1/(k+rank)`, k=60), **#12 prompt template**, **#13 output schema**, **#14 citation format**,
  **#15 confidence**, **#16 log taxonomy**, **#20 project-structure map**, **#11 storage schema** —
  all in `PHYSICAL_SPEC.md`.
- ✅ **#25 Dedicated assumptions** — `ASSUMPTIONS.md`.
- ✅ **Three-level architecture** (Business/Logical/Physical) — `ARCHITECTURE.md` (+ HLD + PHYSICAL_SPEC).
- ⚠️ **#1 Document parsing** — regex strategy documented; **canonical section-name map + section tree
  still pending** (still uses raw heading titles).

---

# Part D — Bucket A + B: RESOLVED (supersedes the pending lists above)

Bucket **A** (cleaning philosophy) and **all** of Bucket **B** (items 2–11) are now implemented,
tested, and re-run on the 246-file corpus. 98 tests pass.

### A. Cleaning philosophy — ✅ DONE (commit `68566fe`)
Stage 2 is now **controlled normalization** (cosmetic, content-preserving), explicitly split from
**Structural Parsing** (metadata/sections). CRLF→LF, tabs→spaces, prose multi-space collapse — with a
`_is_tabular` guard so tables / aligned columns / signatures keep their spacing. Controlled XBRL trim
removes only the leading machine blob + isolated tag lines. Verified: 0/246 files contain `us-gaap:`;
`FORM 10-K`, pipe tables, and `$` figures preserved.

### B. Small hardening — ✅ DONE
2. **SHA-256 + `data/raw_index.json`** (incremental indexing) — `run_ingest` fingerprints every filing
   into a typed `Document` catalog and returns `report["changed"]` (new/modified docs). No timestamps
   (determinism preserved). (commit `c93b1c1`)
3. **Controlled-normalization sub-steps** — explicit CRLF→LF, tabs→spaces, table-safe multi-space
   collapse. (part of A, commit `68566fe`)
4. **Metadata fields** — added `document_id`, `source` (from header), `industry` (curated GICS table
   in `src/reference.py`, `""` for unknown tickers). **Decision: keep `form`** (not `filing_type`) —
   used across filters/citations/tests; header "Filing Type" maps onto it. (commit `777b5c8`)
5. **Canonical section-name map + section tree** — 10-K sections normalized to standard SEC names +
   `SectionSpan.part` (Part I–IV) from the fixed structure; 10-Q keeps detected titles (Part-ambiguous,
   never guessed). Grouping by `part` reconstructs the tree. (commit `42de3e4`)
6. **Chunk sizing** — **Decision: keep char-based, reframed as a MAX cap** (semantic-hierarchical, not
   fixed, and NOT switched to token sizing). Field renamed `chunk_size`→`chunk_max_chars`; docs updated;
   verified ~98% of a filing's chunks land below the cap. (commit `b241f4c`)
7. **Enrichment header** — now includes **Ticker & Quarter** (`Quarter: FY` for annual). (commit `b241f4c`)
8. **Typed `Document` and `EmbeddingRecord`** models — `embed.py` persists `list[EmbeddingRecord]`. (commit `c93b1c1`)
9. **Chroma record `hash`** — `Chunk.content_hash = sha256(text)` flows to Chroma metadata
   (`created_at` intentionally omitted for determinism). (commit `b241f4c`)
10. **Collection name** — **Decision: model-namespaced** (e.g. `sec_filings__BAAI-bge-large-en-v1.5`,
    via `settings.collection_name`). Rationale: a model change ⇒ a fresh index, preventing dimension/
    space mismatches between vectors from different models (this is exactly what made the later switch
    to bge embeddings a clean roll-over). Already implemented; decision recorded.
11. **Project structure** — **Decision: keep the flat `src/` + `src/pipeline/` layout for the MVP;
    do NOT refactor into per-concern folders now.** Rationale: the pipeline is already a clean linear
    sequence of one module per stage; a package rename mid-build adds churn and import risk with no
    functional benefit. Phase 2 will add `retrieval`/`generation`/`frontend` modules under `src/` when
    that code exists (natural per-concern separation without a disruptive refactor).

---

# Part E — Phase 2: BUILT (commits P1–P22)

The online retrieval + generation layer is implemented and tested (209 tests). See
`RETRIEVAL_DESIGN.md` (TDS) and `ADR.md`. Everything before the single Claude call is deterministic
or local ML; refusals make zero LLM calls.

### C. Phase 2 build — ✅ DONE
12. **Retrieval** — validate → classify → extract → hard filter → plan → hybrid (vector+BM25) → RRF
    (k=60) → hydrate → rerank → dedup → evidence, in `src/retrieval/`. (P3–P12, P17)
13. **Single LLM call** — `src/generation/generate.py` (LangChain ChatOpenAI via OpenRouter,
    structured output, one request); prompt builder cite-or-refuse + versioned. (P14, P15)
    *Provider later switched from Claude to OpenAI-via-OpenRouter, and embeddings to local bge — see
    ADR-013/014.*
14. **Confidence score** — deterministic similarity bands in `guardrails.py`, overrides the model's. (P13)
15. **Per-query logging** + **evaluation framework** — `query_log.py` (JSONL) + `src/eval/`: 25-case
    golden set, retrieval metrics (Recall/Precision@k, MRR, NDCG), **A/B harness** (vector vs BM25 vs
    hybrid vs +rerank), **RAGAS** generation grading, **LangSmith** tracing, JSON+HTML reports with
    **regression** diff, and a Streamlit dashboard. (P18, P21, EV1–EV6 — see `EVALUATION.md`)
16. **Debug UI** (Streamlit) `src/frontend/app.py` + **FastAPI** `src/api/main.py`. (P19, P20)
17. **Cost & latency tracking** — `query_log.py` (Claude pricing, wall-clock latency). (P18)

Two spec deltas, both intentional: query logs are one JSONL (`data/logs/queries.jsonl`) rather than
per-file; the cross-encoder reranker ships as an optional dep with an identity fallback.

### D. Real runs — still deferred (need keys / compute, not code)
18. **Real embed run** (local bge, `sentence-transformers`, ~32K chunks) → populate `data/embeddings/`.
19. **Real Chroma + BM25 build** (`python -m src.pipeline.store`) after #18.
20. **Live eval** (`python -m src.eval.run_eval`) + live answers (`OPENROUTER_API_KEY`).
21. **Cross-encoder reranker** — `pip install sentence-transformers` to activate (else identity fallback).

# Design Audit — target design vs. current implementation

Audit of the current codebase (commits through `docs: ingestion README`) against the refined design
(controlled normalization; Normalization vs Structural Parsing split; 10-stage pipeline).

**Status legend:** ✅ implemented & matches · ⚠️ partial · ↔️ divergent (built differently) ·
❌ not implemented. **Decision column is "defer" everywhere — no changes made from this audit.**

## Headline
- The **offline pipeline (Stages 1–8) is built, tested (82 tests), observable, and documented** — but
  it reflects the *earlier* "aggressive clean" decision, **not** the new controlled-normalization one.
- The biggest gaps are **(1) the cleaning philosophy change**, **(2) a dedicated Stage 0 discovery
  artifact**, and **(3) all of Phase 2** (retrieval, fusion, single LLM call, debug UI).

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

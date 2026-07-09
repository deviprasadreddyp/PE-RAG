# SEC RAG System — High-Level Design (MVP)

> The source design doc for PE-RAG. `agents.md` encodes these decisions as enforceable rules and
> skills; this file is the "why." The framing: **build an observable ingestion & retrieval
> pipeline**, not "a RAG." The evaluator is judging the engineering process, so every stage must be
> inspectable.

## 1. Objective
Enable a private-equity analyst to ask natural-language questions over SEC filings and receive
grounded, citation-backed answers from a **single LLM API call**. Prioritize trustworthiness,
explainability, traceability, maintainability, and extensibility. The MVP validates business value
while establishing an architecture that can evolve to production.

## 2. Engineering principles
- **Simplicity over unnecessary complexity** — the simplest architecture that solves it reliably.
- **Deterministic wherever possible** — metadata extraction, parsing, section detection, retrieval,
  and citations are deterministic. LLMs are reserved for natural-language generation only.
- **Every stage is observable** — every pipeline stage persists its output; nothing is a black box;
  developers can inspect every intermediate artifact.
- **Dataset-driven decisions** — adapt to the characteristics of SEC filings, not generic RAG defaults.

## 3. Pipeline
```
SEC corpus → Ingestion → Cleaning → Metadata Extraction → Section Detection → Chunk Generation
           → Chunk Enrichment → Embedding Generation → Vector Store
   query →  Metadata Parsing (deterministic) → Hybrid Retrieval (vector + BM25 → fusion → top-k)
           → Context Builder → Prompt Builder → Single LLM Call → Grounded Response
```

## 4. Stages (each persists an inspectable artifact)
1. **Ingestion** — read every filing; validate encoding, existence, filename format; store raw,
   unmodified → `data/raw/`.
2. **Cleaning** — remove retrieval noise (repeated whitespace, XML artifacts, XBRL namespace
   declarations, repeated technical identifiers, formatting) while preserving business text, section
   titles, financial terminology, and tables where possible → `data/cleaned/`.
3. **Metadata Extraction** — never an LLM. From filename + manifest + document headers:
   company, ticker, filing_type, filing_date, report_period, year, quarter, source_file →
   `data/metadata/`.
4. **Section Detection** — detect SEC sections (Business, Risk Factors, MD&A, Legal Proceedings,
   Financial Statements, Cybersecurity, …) with `{section_name, start, end}` → `data/sections/`.
5. **Chunk Generation** — chunk **within sections**, never across unrelated sections; recursive
   character splitting; size/overlap chosen after inspecting the corpus; `{chunk_id, section, text}`
   → `data/chunks/`.
6. **Chunk Enrichment** — prepend `Company / Filing / Year / Section` to each chunk before embedding
   to improve embedding quality.
7. **Embedding Generation** — embed enriched chunks; store `{chunk_id, embedding, metadata}` →
   `data/embeddings/`.
8. **Vector Store** — ChromaDB (persistent, strong metadata support, simple deployment) holding
   embedding + metadata + chunk text + source/section/year/company/filing_type → `data/vectorstore/`.

## 5. Retrieval
Question → deterministic metadata parsing → hybrid search (vector + BM25 → fusion) → top-k →
context builder. No LLM in retrieval.

## 6. Prompt & LLM
One prompt from (question + retrieved context + metadata). Rules: answer only from supplied context;
never invent facts; provide citations; if unavailable, say so. **Exactly one API call** → grounded
answer.

## 7. Response shape
Executive summary · detailed comparison · supporting evidence · citations · source filings.

## 8. Observability & logging
The full chain is inspectable: raw → cleaned → metadata → sections → chunks → embeddings →
retrieved chunks → prompt → final answer. Every query logs: question, retrieved chunk IDs,
similarity scores, prompt, response, latency, tokens, cost, timestamp → `data/logs/`.

## 9. Evaluation
An evaluation dataset (`evaluation/`): per question — expected companies, expected filing, expected
section, retrieved chunks, answer, and manual grounding verification.

## 10. Frontend
Simple: dark background, input box, submit, spinner, markdown answer, expandable citations. A
**developer debug mode** exposes the whole pipeline for a query: parsed metadata filters → retrieved
chunks → similarity scores → final prompt → LLM response → token usage → latency. Normal mode shows
only the answer.

## 11. Directory structure
```
src/ · frontend/ · data/{raw,cleaned,metadata,sections,chunks,embeddings,vectorstore,logs}
evaluation/ · prompt_iterations/ · architecture/ · README.md
```

## 12. Future roadmap (document only — do NOT build now)
Automated SEC ingestion · incremental indexing · reranker · parent-child retrieval · evaluation
dashboard · user feedback · authentication · role-based access · production monitoring · scheduled
updates.

## 13. Deliverables
README · architecture diagram · prompt iteration log · assumptions · retrieval code · frontend ·
evaluation notes · recorded demo.

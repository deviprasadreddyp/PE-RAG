---
name: architecture-designer
description: Design the shape of a system or component before coding — modules, interfaces/APIs, data models, control/data flow, error handling, extensibility, and scaling. Also covers dependency hygiene (module boundaries, circular deps) and data-store design (schemas, indexes, migrations). Use after requirements are clear and before implementation-planner. For RAG, design the ingestion → index → retrieval → generation pipeline and its contracts.
---

# Architecture Designer

Turn a clear requirements brief into a design. No production code until the shape is agreed.

## When to invoke
- A new component or system needs structure.
- An existing design needs review for boundaries, coupling, or scaling.
- Before `implementation-planner`.

## Process
1. **Decompose into modules** with a single responsibility each. Name them. State what each
   owns and does NOT own.
2. **Define interfaces/contracts** between modules: function/API signatures, request/response
   schemas, error types. Contracts first — they let phases be built and tested independently.
3. **Data model.** Entities, fields, types, relationships. For stores: keys, indexes,
   normalization vs denormalization, and a **migration story** (how the schema evolves safely).
4. **Data + control flow.** Trace a request end to end. Where does data enter, transform, persist,
   leave? Draw it (ASCII/mermaid is fine).
5. **Error handling strategy.** Where failures occur, how they propagate, what's retryable,
   what the user sees. (Coordinate with `reliability-engineer`.)
6. **Extensibility & scaling.** What's likely to change? Isolate it behind an interface.
   Where does this break at 10x / 100x data or traffic?
7. **Dependency hygiene.** Draw the module dependency graph. No cycles. Depend on abstractions,
   not concretions. Flag unused or overly-broad dependencies.
8. **Tradeoffs.** For each significant choice, invoke `tradeoff-analyzer` and record why.

## RAG reference architecture (adapt, don't cargo-cult)
```
ingestion:  load → clean (strip XBRL) → section-split → chunk → embed → upsert
                       │                                   │
                  metadata extract ──────────────────────►│  (ticker, form, period, cik, section, url)
storage:    vector index (+ HNSW/IVF params)  |  metadata store  |  original-doc store
retrieval:  query → (rewrite/expand) → filter by metadata → hybrid search (dense+BM25)
                 → rerank → assemble context (with citations, token budget)
generation: prompt (grounded, cite-or-refuse) → structured output → validate → answer + sources
```
Design the **contracts** between these (e.g. `Chunk`, `RetrievalResult`, `Citation`, `Answer`)
so ingestion, retrieval, and generation are independently testable and swappable.

## Output
A **Design Doc**: module map · interfaces/schemas · data model + indexes · flow diagram ·
error strategy · extensibility notes · key tradeoffs. End with the open risks.

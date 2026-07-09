# 02 — Technical Spec: <feature name>

> Fill this out AFTER the product spec is answered and BEFORE the implementation plan.
> Design the shape before writing code. Reference the skills you will follow.
> Copy this file to `features/active/<feature-name>/02-technical-spec.md`.

## Summary
One paragraph: what changes in the system and where it fits in the ingestion → retrieval →
generation pipeline (see the diagram in `agents.md`).

## Skills this feature relies on
List the `skills/*.md` that govern this work (e.g. `chunking-strategy`, `hybrid-retrieval`,
`single-call-rag`). Read them before designing. Note any place you must deviate — and why.

## Components touched / added
For each module (`src/ingest|index|retrieval|generation`, `frontend/app.py`, `scripts/`):
- **Module:** what it does, what it owns, what it must NOT own.
- **New vs modified.**

## Interfaces / contracts
Concrete signatures and schemas. Depend on the `Embedder` / `VectorStore` protocols, not on Chroma/
Voyage directly. Example shape:
```python
class Chunk(TypedDict):
    id: str            # stable; used for idempotent upsert
    text: str
    ticker: str; company: str; form: str      # "10-K" | "10-Q"
    filing_date: str; fiscal_period: str       # e.g. "2024Q3"
    cik: str; section: str; source_url: str; chunk_index: int

# retrieval
def retrieve(query: str, filters: dict, k: int) -> list[RetrievalResult]: ...
# generation — THE single call
def answer(question: str) -> Answer:  # {answer: str, sources: list[Citation], usage: dict}
```

## Data model / metadata
- Confirm the chunk metadata schema (`skills/metadata-schema`). Any new field? Justify it.
- Vector store collection name, distance metric, and any index params (HNSW `M`/`ef`).
- How query filters map to metadata `where` clauses.

## Data & control flow
Trace one request end to end for this feature. Where does the metadata filter apply? Where is the
single Claude call? Where do citations come from? (ASCII/mermaid fine.)

## The single-call boundary
State explicitly: what runs BEFORE the one Claude call (retrieval, rerank, query parse, assembly)
and what happens IN the call. Confirm no second LLM call is on the answer path (non-negotiable #1).

## Error handling & failure modes
- Empty retrieval → refusal path.
- Vector store / embedding API down → behavior.
- Context over budget → explicit lowest-rank drop, never silent truncation.
- Malformed / off-topic question.

## Cost & latency
- Estimated tokens per query (context size × model) and $ per query; model choice per stage.
- Where prompt caching applies (stable system prompt prefix).

## Tradeoffs & alternatives
Any decision with more than one reasonable answer: what you chose, what you gave up, when to revisit.

## Open risks
What could still be wrong after this is built.

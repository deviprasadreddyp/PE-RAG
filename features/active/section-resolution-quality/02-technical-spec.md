# 02 - Technical Spec: Section Resolution Quality

## Summary
Add deterministic semantic section resolution after chunking and at retrieval hydration time. The resolver extracts strong heading/content signals from chunk text, compares them against weak section labels, assigns a final section, records confidence/source/metadata quality, and lets retrieval boost or diversify based on either the final section or section signals.

## Skills This Feature Relies On
- `section-detection`: deterministic SEC item/section handling.
- `chunking-strategy`: preserve sections/tables and full metadata.
- `metadata-schema`: Chroma-safe metadata fields only.
- `hybrid-retrieval`: metadata filter, hybrid search, RRF, rerank, deterministic boosts.
- `evaluation`: measure after rebuild before claiming improvement.

## Components Touched / Added
- **New:** `src/pipeline/section_resolution.py` owns deterministic signal extraction and section resolution.
- **Modified:** `src/schemas.py` adds Chroma-safe chunk signal fields with defaults.
- **Modified:** `src/pipeline/chunk.py` applies section resolution when creating chunks on the next rebuild.
- **Modified:** `src/retrieval/vector_retriever.py` applies runtime resolution when hydrating current persisted records, without mutating artifacts.
- **Modified:** `src/retrieval/metadata_parser.py` and `retrieval_planner.py` strengthen trend/financial query intent.
- **Modified:** `src/retrieval/retrieval_pipeline.py` boosts and selects evidence using final sections plus signals.
- **Modified:** eval golden set handles the impossible JPM 2024 10-K case.

## Interfaces / Contracts
```python
def resolve_section(text: str, current_section: str) -> SectionResolution: ...
def apply_section_resolution(chunk: Chunk) -> Chunk: ...
```

New chunk metadata fields are scalar:
- `section_original: str`
- `section_confidence: float`
- `section_source: str`
- `section_signals: str`
- `has_risk_heading: bool`
- `has_mda_heading: bool`
- `has_legal_heading: bool`
- `has_business_heading: bool`
- `has_financial_table: bool`
- `has_revenue_table: bool`
- `metadata_quality: float`

## Data Model / Metadata
The fields are optional defaults on `Chunk`, so existing Chroma/BM25 records continue to hydrate. On rebuild, they are persisted in chunk artifacts and index metadata.

## Data & Control Flow
```text
cleaned + sections -> chunk -> resolve section/signals -> enrich/embed/store
query -> parse -> hybrid retrieve -> hydrate + runtime resolve -> RRF/boost -> rerank
      -> section-aware diversify -> context -> one generation call
```

## Single-Call Boundary
All new logic runs before the final generation call and is deterministic. It does not introduce any LLM calls.

## Failure Modes
- If no strong signal exists, keep the original section.
- If the requested company/form/year is absent, keep refusal behavior.
- If current artifacts lack new fields, runtime hydration computes them best-effort from text.

## Cost & Latency
Regex/string scanning per candidate/chunk. No API cost. Runtime overhead is tiny versus embedding, reranking, or generation.

## Tradeoffs
Using scalar signal fields instead of a list keeps Chroma compatibility but is less elegant than structured metadata. The raw `section_signals` string preserves inspectability.

## Open Risks
Some filings may have section headings embedded in tables of contents. The resolver therefore requires stronger body/content signals before overriding high-confidence canonical labels.

# 02 - Technical Spec: Full Rechunk + Full Index

## Summary
Improve the offline deterministic pipeline before rebuilding the full index: extract useful XBRL/cover facts into metadata, strip only XBRL infrastructure from cleaned text, improve table-preserving chunking, then regenerate chunks, embeddings, Chroma, and BM25 for the full corpus.

## Skills this feature relies on
- `document-cleaning`
- `metadata-schema`
- `section-detection`
- `chunking-strategy`
- `chunk-enrichment`
- `embedding-generation`
- `hybrid-retrieval`
- `evaluation`

## Components touched / added
- **`src/schemas.py`:** extend `DocMetadata` with XBRL-derived scalar fields.
- **`src/pipeline/metadata.py`:** extract metadata from header, XML tags when present, tag-soup fallbacks, and cover text.
- **`src/pipeline/clean.py`:** remove XML/XBRL infrastructure conservatively while preserving narrative and tables.
- **`src/pipeline/chunk.py`:** table-aware chunks with nearby header context and stable chunk IDs.
- **`src/pipeline/enrich.py`:** include richer fiscal metadata in embed headers.
- **`src/eval/datasets/golden.jsonl`:** expand deterministic quality cases.

## Interfaces / contracts
- `DocMetadata` remains Chroma-safe: only `str`, `int`, `float`, and `bool`.
- Existing fields remain backward-compatible: `company`, `ticker`, `form`, `filing_date`, `report_period`, `fiscal_period`, `year`, `quarter`, `cik`.
- New fields include fiscal-year focus, fiscal-period focus, current fiscal year-end, amendment details, incorporation state/country, and shares outstanding.
- Retrieval still depends on `VectorStore` / `Embedder` protocols, not Chroma/OpenAI directly.

## Data model / metadata
New metadata is used for filtering/debugging/citations and stored on every chunk. `year` remains the fiscal-year filter field for existing retrieval code; `fiscal_year` mirrors it when available.

## Data & control flow
`raw -> clean -> metadata -> sections -> chunk -> enrich -> embed -> store`. Query-time behavior is unchanged: deterministic parse/filter/retrieve/rerank/context, then one generation call.

## The single-call boundary
All rebuild work happens offline. The answer path still performs exactly one final generation call after deterministic retrieval and prompt assembly.

## Error handling & failure modes
- Missing XBRL tags fall back to header/filename/cover-derived values.
- Cleaning keeps text when uncertain.
- Oversized table rows can split as last resort, but table row boundaries are otherwise preserved.
- Empty retrieval still refuses before generation.

## Cost & latency
Full rebuild embeds all regenerated chunks once using OpenAI batch embeddings and cache. Re-runs reuse `data/.embedding_cache` for unchanged embed text.

## Tradeoffs & alternatives
- We avoid a full XBRL parser for MVP speed; this extracts high-value facts only.
- We preserve table formatting instead of converting tables to normalized data, because citations need verbatim source text.

## Open risks
- Some corpus files have compressed tag-soup, so XBRL fact extraction may rely on header/cover fallbacks.
- Full dense embedding time depends on OpenAI rate limits.

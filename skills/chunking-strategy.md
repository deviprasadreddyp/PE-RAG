# Skill: chunking-strategy

**Purpose.** Split a cleaned filing into retrieval chunks that are precise enough to rank and
self-contained enough to answer, with fiscal metadata on every chunk. Chunking silently determines
retrieval quality — get it right here.

**When to invoke.** Work in `src/ingest/chunker.py`; tuning chunk size/overlap.

## How to do it (SEC-specific)
1. **Clean first.** Input is the XBRL-stripped body from `document-ingestion`. Never chunk raw text.
2. **Split on structure, not bytes.** 10-K/10-Q have canonical items:
   - 10-K: Item 1 Business, 1A Risk Factors, 3 Legal, 7 MD&A, 7A Market Risk, 8 Financial Statements.
   - 10-Q: Financial Statements, MD&A, 3 Market Risk, 4 Controls, Part II Legal Proceedings.
   Detect item headings and split there first; recurse within long sections by paragraph → sentence
   with a size cap.
3. **Keep tables whole.** Never split a financial table mid-row — a row without its header/period is
   unciteable and its numbers become meaningless. Detect table-like blocks (pipe/tab/aligned-number
   runs) and emit them as their own chunk.
4. **Attach metadata to every chunk** (`skills/metadata-schema`), including `section` (e.g.
   "Item 7 MD&A") and a stable `id` for idempotent upsert (e.g. `f"{ticker}_{form}_{period}_{i}"`).
5. **Size:** start ~500–1000 tokens for prose, table chunks sized to stay whole. Overlap ~10–15%.
   The right size is empirical — sweep a few and let `skills/evaluation` decide on the labeled set.

## Bad example
```python
# BAD: fixed 1000-char slices — cuts sentences, splits tables, drops all metadata
chunks = [text[i:i+1000] for i in range(0, len(text), 1000)]
store.add(chunks)          # no ticker/period/section; a revenue table is now 3 half-tables
```

## Good example
```python
ITEM = re.compile(r"^\s*(Item\s+\d+[A-Z]?\.?\s+[A-Z][^\n]{0,60})", re.M)

def chunk(meta: dict, body: str) -> list[Chunk]:
    out, idx = [], 0
    for section, text in split_on_items(body, ITEM):      # section-aware first
        for block in split_preserving_tables(text, target_tokens=800, overlap=0.12):
            out.append(Chunk(
                id=f"{meta['ticker']}_{meta['form']}_{meta['fiscal_period']}_{idx}",
                text=block, section=section, chunk_index=idx, **meta,   # full metadata
            ))
            idx += 1
    return out
```

## Failure modes seen
- Blind fixed-size splitting that cuts tables and sentences → header-less number fragments.
- Chunks with no `section`/`period` → retrieval can't scope; citations are vague.
- Huge chunks that bury the answer and blow the context budget; or tiny chunks that can't answer.
- Overlap set so high it floods top-k with near-duplicates (dedupe at assembly — `context-assembly`).

## MUST NOT
- MUST NOT split a financial table across chunks.
- MUST NOT emit a chunk missing the metadata schema (ticker/company/form/period/section/url).
- MUST NOT paraphrase, reformat, or round numbers while chunking — preserve text verbatim.
- MUST NOT pick a chunk size by feel and call it done — justify it against the eval set.

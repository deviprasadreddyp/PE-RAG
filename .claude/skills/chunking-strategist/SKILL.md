---
name: chunking-strategist
description: Decide how to split documents into retrieval chunks and what metadata each chunk carries. Covers strategy (fixed vs recursive vs section/semantic), size and overlap, table and list handling, and attaching filter metadata. Use when designing or tuning ingestion for The-RAG's SEC filings, where section structure, tables, exact numbers, and fiscal metadata all matter.
---

# Chunking Strategist

Chunking silently determines retrieval quality. A chunk must be small enough to be precise and
large enough to be self-contained and answerable. For SEC filings, structure and metadata
matter more than raw size.

## When to invoke
- Designing or tuning how filings are split before embedding.
- Retrieval is returning fragments that are too small to answer, or too big/noisy to rank.

## SEC-filing-specific strategy
1. **Clean first.** Strip the leading XBRL/us-gaap tag blob and boilerplate before chunking
   (→ `financial-document-handler`). Chunking raw XBRL wastes the index and pollutes retrieval.
2. **Split on structure, not bytes.** 10-K/10-Q have canonical items:
   - 10-K: Item 1 Business, 1A Risk Factors, 7 MD&A, 7A Market Risk, 8 Financial Statements, etc.
   - 10-Q: Financial Statements, MD&A, controls, legal proceedings.
   Split on these boundaries first; recurse within long sections.
3. **Recursive splitting inside sections** by paragraph → sentence, with a size cap.
4. **Keep tables intact.** Never split a financial table mid-row. A row divorced from its header
   loses meaning and its numbers become unciteable. Consider table-to-markdown and one-table-per-chunk.
5. **Overlap** modestly (e.g. 10–15%) so cross-boundary context isn't lost — but overlap
   duplicates tokens (cost) and can inflate near-duplicate hits; dedupe at assembly.

## Metadata every chunk MUST carry
`ticker` · `company` · `form` (10-K/10-Q) · `filing_date` · `fiscal_period`/`quarter` ·
`cik` · `section` (e.g. "Item 7 MD&A") · `source_url` · `chunk_index`.
This is what makes "AAPL MD&A for Q3 2024" a metadata filter instead of a lucky vector hit.

## Sizing guidance (measure, don't guess)
- Start ~500–1000 tokens/chunk for prose; tables sized to stay whole.
- The "right" size is empirical — sweep a few sizes and let `retrieval-evaluator` decide on a
  labeled query set. Different sections may warrant different sizes.

## Anti-patterns
- Blind fixed-character splitting that cuts sentences, tables, and numbers.
- Chunks with no section/period metadata (retrieval can't scope; citations are vague).
- Huge chunks that bury the answer and blow the context budget.
- Tiny chunks that can't answer anything on their own.

## Output
A concrete chunking spec (clean → section-split → recurse → table rule → size/overlap → metadata),
plus a recommendation to A/B a couple of configs via `retrieval-evaluator`.

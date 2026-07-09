---
name: financial-document-handler
description: Correctly parse and handle SEC EDGAR filings (10-K/10-Q) in edgar_corpus/ — read the metadata header, strip the XBRL/us-gaap noise blob, identify filing sections/items, preserve tables and exact figures, normalize fiscal periods, and produce citations. Use for any ingestion, parsing, cleaning, or answer-formatting work that touches the filings or their numbers.
---

# Financial Document Handler

The corpus is SEC filings, not clean prose. Handling them correctly is the difference between a
trustworthy financial RAG and one that cites wrong numbers. Get the parsing right at the source.

## Corpus facts (see also `.claude/CLAUDE.md`)
- 247 `.txt` filings + `manifest.json` in `edgar_corpus/`, ~54 tickers, forms 10-K and 10-Q.
- Filename: `TICKER_FORM_[PERIOD]_YYYY-MM-DD_full.txt` — `PERIOD` (e.g. `2024Q3`) may be absent.
- File layout: **metadata header** (Company, Ticker, Filing Type, Filing Date, Report Period,
  Quarter, CIK, Source, URL) → `====` separator → **filing body**.
- The body **opens with a large XBRL / us-gaap tag blob** (machine data, no prose value) before
  the human-readable filing text.

## Rules

**1. Read metadata from the header, not just the filename.**
Parse the header block for `ticker`, `company`, `form`, `filing_date`, `report_period`,
`quarter`, `cik`, `source_url`. The filename is a fallback/cross-check, not the source of truth
(period is missing from some filenames but present in the header).

**2. Strip the XBRL/us-gaap blob before anything else.**
Detect and remove the leading run of `us-gaap:`/`srt:`/`aapl:`-style tag soup and CIK-date
concatenations. Chunking or embedding this pollutes retrieval and wastes cost. Keep the
human-readable body that starts around the "FORM 10-K/10-Q" / cover-page text.

**3. Identify sections/items.** Locate canonical items (10-K: Item 1, 1A Risk Factors, 7 MD&A,
7A, 8 Financial Statements; 10-Q: financial statements, MD&A, controls, legal). Tag each chunk
with its section so retrieval can scope and citations are precise.

**4. Preserve tables and exact figures.** Financial tables carry the answers. Keep rows with
their headers; don't split a table across chunks; keep units ($, thousands, millions), signs,
and the period column. Never round, reformat, or paraphrase a filed number.

**5. Normalize fiscal periods carefully.** Fiscal year ≠ calendar year (e.g. Apple's FY ends late
September). Distinguish `filing_date` (when filed) from `report_period` (what it covers). Make
period a filterable field so "Q3 2024" resolves unambiguously.

**6. Produce citations.** Every extracted fact/answer traces to `ticker + form + period + section`
and the `source_url`. Answers about numbers must be citeable to the exact filing and section.

## Anti-patterns
- Trusting the filename when the header disagrees. Embedding XBRL tag soup. Splitting tables.
- Paraphrasing figures or dropping units/periods. Confusing filing date with report period.
- Mixing two companies' or two periods' numbers in one chunk or one answer.

## Output
Clean, structured filing content (metadata + sectioned, table-preserving body) ready for
`chunking-strategist`, plus the citation fields for every unit of text.

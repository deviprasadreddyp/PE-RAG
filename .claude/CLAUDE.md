# The-RAG — Project Guide

Retrieval-Augmented Generation over **SEC EDGAR filings** (10-K annual reports, 10-Q
quarterly reports). The goal is a system that answers financial questions grounded in
the source filings, with citations, over ~54 large-cap US tickers.

## Corpus

- `edgar_corpus/` — 247 `.txt` filings + `manifest.json`.
- Filename convention: `TICKER_FORM_[PERIOD]_YYYY-MM-DD_full.txt`
  (e.g. `AAPL_10K_2022Q3_2022-10-28_full.txt`). `PERIOD` is not always present.
- Each file starts with a **metadata header** (Company, Ticker, Filing Type, Filing Date,
  Report Period, Quarter, CIK, Source, URL) then a `====` separator, then the filing body.
- ⚠️ The body begins with a large **XBRL / us-gaap tag blob** (machine data) before the
  human-readable 10-K/10-Q text. This noise must be stripped or isolated before chunking.
- Filings contain **financial tables and exact figures** — chunking and answering must
  preserve numbers, units, and fiscal periods faithfully. Never let the model invent numbers.

## Domain rules that everything must respect

1. **Fiscal metadata is a first-class filter.** Every chunk must carry `ticker`, `form`
   (10-K/10-Q), `filing_date`, `fiscal_period`/`quarter`, `cik`, and `source_url`.
   Most user questions are scoped by company + period ("AAPL revenue in Q3 2024").
2. **Citations are mandatory.** Every answer traces back to `ticker + form + period + section`
   and ideally the source URL. Financial answers without provenance are unacceptable.
3. **Numbers are load-bearing.** Do not paraphrase figures. Preserve units ($, thousands,
   millions), signs, and periods exactly as filed.
4. **Cross-company / cross-period comparison** is a core query type — retrieval must be able
   to fan out across tickers/periods, not just top-k over one blob.

## Working conventions

- Design and plan before coding; implement in independently testable phases.
- Keep ingestion, retrieval, and generation as separate, testable modules.
- Store secrets in env vars / `.env` (git-ignored) — never hardcode API keys.
- The latest Claude models are the default for generation/embeddings work
  (Opus 4.8, Sonnet 5, Haiku 4.5). Check the `claude-api` skill before writing API code.

## Skills

This project ships a skill library under `.claude/skills/` that makes Claude work like a
staff engineer: understand → design → plan → implement → review → test → optimize → document.
See `.claude/skills/README.md` for the full index and when each fires.

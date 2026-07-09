# Expected — case 01 (multi-company risk comparison)

## Retrieval behavior
- Resolves company names → tickers: Apple→AAPL, Tesla→TSLA, JPMorgan→JPM.
- Builds a metadata filter: `ticker ∈ {AAPL, TSLA, JPM}`, `form = "10-K"`, most-recent period each.
- **Fans out per company** so all three are represented — no single company crowds out the others.
- Targets the Risk Factors section (10-K Item 1A) via section metadata / query terms.

## Answer behavior
- One-line takeaway, then a per-company summary, then common vs. distinct risks (table or parallel
  bullets).
- Every claim carries an inline citation tag (e.g. `[AAPL 10-K FY2024 · Item 1A Risk Factors]`).
- Risks reflect each company's actual filing (e.g. TSLA: supply chain / demand / regulatory-EV;
  JPM: credit / interest-rate / regulatory-capital; AAPL: supply concentration / China / competition)
  — no risk attributed to the wrong company.
- Sources list links each cited filing's `source_url`.

## Rules that must hold
- **Exactly one Claude call** produces the answer (retrieval/rerank happen before it).
- Cite-or-refuse: if a company's 10-K isn't retrievable, that's stated, not invented.
- No fabricated risks or numbers; company/period isolation respected.

## Skills that should have been used
`metadata-schema`, `hybrid-retrieval`, `context-assembly`, `single-call-rag`, `prompt-template`,
`answer-grounding`.

## Pass criteria
- [ ] All three companies covered from their 10-K Risk Factors.
- [ ] Metadata filter used (not a whole-corpus rank); fan-out across the three tickers.
- [ ] Structured comparison (common vs distinct) with inline citations + source links.
- [ ] Single LLM call; no fabricated content; no cross-company misattribution.

# Expected — case 02 (single-company cross-period trend)

## Retrieval behavior
- Resolves NVIDIA → NVDA; filter `ticker = "NVDA"`.
- **Cross-period retrieval:** pulls multiple fiscal periods (fans out across the last ~2 years of
  available NVDA filings), not just one filing.
- Filters/targets by `fiscal_period` (what the filing covers), **not** `filing_date`.
- Targets revenue / MD&A / financial-statement sections.

## Answer behavior
- Reports specific revenue figures **each tagged with its fiscal period**, verbatim with units
  ($ in millions/billions) — no rounding, no dropped units.
- Summarizes the trend (direction + magnitude) grounded only in the retrieved figures.
- Inline citations per figure (e.g. `[NVDA 10-K FY2024 · Item 7 MD&A]`); source links listed.
- If a period isn't in the corpus, says so rather than interpolating.

## Rules that must hold
- Exactly one Claude call for the answer.
- Numeric fidelity: figures/units/periods exact. No invented numbers.
- Uses `fiscal_period` axis, not filing date, to place the numbers in time.

## Skills that should have been used
`metadata-schema`, `hybrid-retrieval`, `context-assembly`, `single-call-rag`, `answer-grounding`.

## Pass criteria
- [ ] Multiple periods retrieved for NVDA (trend, not a single point).
- [ ] Figures exact with units + fiscal period; no rounding.
- [ ] Correct time axis (fiscal_period), not filing_date.
- [ ] Single LLM call; citations present; missing periods acknowledged, not invented.

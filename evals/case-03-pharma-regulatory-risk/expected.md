# Expected — case 03 (sector / thematic, no explicit ticker)

## Retrieval behavior
- No ticker named → the system must map "major pharmaceutical companies" to the pharma tickers in the
  corpus (e.g. JNJ, PFE, MRK, ABBV, LLY, TMO) via a sector/alias mapping — not return a single
  company or the whole corpus.
- Fans out across those tickers; targets regulatory / risk-factor / legal-proceedings sections.
- Thematic query (dense-heavy) but still metadata-scoped to the pharma subset.

## Answer behavior
- Synthesizes common regulatory risks (FDA approval, pricing/reimbursement, patent/IP, compliance)
  **grounded in the cited filings**, with per-company specifics and how each addresses them.
- Every claim cited to a specific company's filing; source links listed.
- Only companies actually present in the corpus are included; scope stated.

## Rules that must hold
- Exactly one Claude call for the answer.
- No fabricated companies or risks; claims traceable to retrieved chunks.
- If the sector mapping is uncertain, the system states which companies it treated as "major pharma."

## Skills that should have been used
`metadata-schema` (sector→ticker mapping), `hybrid-retrieval`, `context-assembly`, `single-call-rag`,
`answer-grounding`.

## Pass criteria
- [ ] Maps the sector to multiple real pharma tickers in the corpus (not one, not all 54).
- [ ] Cross-company synthesis with per-company citations + source links.
- [ ] Single LLM call; grounded; scope of "major pharma" stated.

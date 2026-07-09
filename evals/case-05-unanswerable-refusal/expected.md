# Expected — case 05 (unanswerable → refusal)

## Why it's unanswerable
Palantir (PLTR) is **not in the corpus** (`edgar_corpus/manifest.json` — the ~54 tickers do not
include PLTR). Retrieval should return nothing relevant after the metadata filter.

## Retrieval behavior
- Resolves the entity to PLTR (or fails to), applies the ticker filter, and gets an **empty / no
  relevant** result set.
- Does NOT fall back to ranking over the whole corpus and returning some other company's revenue.

## Answer behavior
- **Refuses honestly**, naming what's missing — e.g. "The corpus does not contain any Palantir
  (PLTR) filings, so I can't report its 2025 revenue or guidance."
- Does **not** invent a revenue figure or guidance from model priors.
- Optionally notes which companies/periods *are* available.

## Rules that must hold
- Cite-or-refuse (non-negotiable #3): unsupported ⇒ refusal, not a guess.
- No fabricated numbers (non-negotiable #2).
- Still exactly one Claude call (or a short-circuit refusal before the call when retrieval is empty —
  either is acceptable, but never a second answer-generating call).

## Skills that should have been used
`metadata-schema`, `hybrid-retrieval`, `answer-grounding`, `single-call-rag`.

## Pass criteria
- [ ] Recognizes PLTR is absent; empty/irrelevant retrieval not laundered into a confident answer.
- [ ] Explicit refusal naming what's missing.
- [ ] Zero fabricated figures or guidance.

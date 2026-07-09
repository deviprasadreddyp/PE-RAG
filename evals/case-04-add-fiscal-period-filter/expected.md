# Expected — case 04 (build eval: fiscal-period range filter)

## Process (the harness workflow must be followed)
- Creates `features/active/fiscal-period-range-filter/` and fills the three templates **in order**
  (`01-product-spec` → `02-technical-spec` → `03-implementation-plan`) before coding.
- Product spec identifies the query type (cross-period trend) and edge cases (open-ended range, no
  filing in range, fiscal ≠ calendar year).
- Reads `metadata-schema` and `hybrid-retrieval` and follows them.

## Implementation
- Extends query parsing to detect a period range ("2023 to 2025", "since 2023", "FY23–FY25") and
  produce a set/range of `fiscal_period` values.
- Maps it to a Chroma `where` clause on `fiscal_period` (the existing metadata field — **no re-index
  needed**; no new chunk field, or if one is added, the plan calls for a re-index and version bump).
- Filters on `fiscal_period`, not `filing_date`; handles fiscal ≠ calendar year.
- Lives in `src/retrieval/` (query parsing / `retriever.py`), depends on the `VectorStore`
  protocol — no direct Chroma coupling in business logic.
- Adds unit tests (range parsing, where-clause construction) and a retrieval test on the eval set.

## Conventions & rules
- Matches existing code style and the `Chunk`/filter conventions.
- Does not touch the single-call generation path; no extra LLM call introduced.
- No fabricated data; no hardcoded keys; no invented metadata field without a re-index plan.

## Pass criteria
- [ ] Feature folder + three filled templates, in order.
- [ ] Range → `fiscal_period` `where` clause; correct time axis; fiscal-year handling.
- [ ] Reuses existing metadata (or plans a re-index if it doesn't); protocol-based, tested.
- [ ] No new LLM call; conventions and non-negotiable rules respected.

# Skill: metadata-schema

**Purpose.** Define the exact metadata every chunk carries and how a natural-language question maps
to metadata filters. For this corpus, metadata filtering is the single highest-leverage retrieval
lever — most questions are scoped by company and/or period.

**When to invoke.** Anywhere a `Chunk` is created or a query filter is built (`ingest/`, `retrieval/`).

## The schema (every chunk, no exceptions)
```python
class Chunk(TypedDict):
    id: str            # stable, unique — used for idempotent upsert
    text: str
    ticker: str        # "AAPL"
    company: str       # "Apple Inc"
    form: str          # "10-K" | "10-Q"   (normalize exactly to these)
    filing_date: str   # ISO "2022-10-28"  (when it was filed)
    fiscal_period: str # "2022Q3" or ""    (what it covers — may be empty for some 10-Ks)
    cik: str           # "0000320193"
    section: str       # "Item 7 MD&A"     (from chunking)
    source_url: str    # SEC EDGAR URL
    chunk_index: int
```
Chroma metadata values must be str/int/float/bool — no None, no lists. Use `""` for a missing period,
never `None`.

## Query → filter mapping
Parse the question for entities and build a Chroma `where` clause. Keep it deterministic (regex /
alias table over ticker+company names, not an LLM guess where avoidable).
```python
# "Compare Apple and Tesla 10-K risk factors for 2024"
filters = {"$and": [
    {"ticker": {"$in": ["AAPL", "TSLA"]}},
    {"form": "10-K"},
    {"fiscal_period": {"$in": ["2024Q3", "2024Q4", "2024"]}},  # fiscal ≠ calendar; widen carefully
]}
```
- `filing_date` = when filed; `fiscal_period` = what it covers. **Filter on `fiscal_period`** for
  "what was X in 2024," not on `filing_date`. Fiscal year ≠ calendar year (Apple's FY ends late Sept).
- Cross-company/cross-period questions produce `$in` filters — fan out, don't force one filing.

## Bad example
```python
# BAD: filtering by filing_date for a "2024 revenue" question; None in metadata; ticker-only guess
where = {"filing_date": "2024"}          # wrong axis — filed-in-2024 ≠ covers-2024
chunk["fiscal_period"] = None            # Chroma rejects None
```

## Good example
```python
def build_where(q: str, aliases: dict[str,str]) -> dict | None:
    tickers = resolve_tickers(q, aliases)       # "JPMorgan" -> "JPM"
    form    = "10-K" if re.search(r"10-?K|annual", q, re.I) else \
              "10-Q" if re.search(r"10-?Q|quarter", q, re.I) else None
    periods = resolve_periods(q)                 # -> ["2024Q3", ...] or []
    clauses = []
    if tickers: clauses.append({"ticker": {"$in": tickers}})
    if form:    clauses.append({"form": form})
    if periods: clauses.append({"fiscal_period": {"$in": periods}})
    return {"$and": clauses} if len(clauses) > 1 else (clauses[0] if clauses else None)
```

## Failure modes seen
- Filtering on `filing_date` instead of `fiscal_period` → returns the wrong year's numbers.
- Putting `None` / lists in chunk metadata → Chroma upsert errors.
- Over-narrow filters (single exact period) → misses the relevant filing; widen the period set.
- Not resolving company names to tickers → "JPMorgan" retrieves nothing (index keys on `JPM`).

## MUST NOT
- MUST NOT ship a chunk missing any schema field.
- MUST NOT confuse `filing_date` with `fiscal_period`.
- MUST NOT rank over the whole corpus when the question names a company/period — filter first.

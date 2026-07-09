# Skill: context-assembly

**Purpose.** Turn the ranked chunks into the single context block injected into the one Claude call:
fit the token budget, dedupe near-duplicates, tag each chunk with a citation label, and never
silently truncate the best chunk.

**When to invoke.** Work in `sec_rag/retrieval/context.py`.

## How to do it
1. **Order best-first** (by rerank score). The model attends best to what's clearly delimited and
   near the top.
2. **Dedupe** near-identical chunks (overlap regions, boilerplate risk-factor language repeated
   across filings) before spending budget on them.
3. **Label each chunk with a citation tag** the model can echo: `[AAPL 10-K FY2024 · Item 7 MD&A]`.
   Include the `source_url` so the front-end can link it.
4. **Budget explicitly.** Count tokens (`claude-api` skill → token counting). Keep context within a
   set budget (leave room for the question + answer). If over budget, **drop the lowest-ranked chunks
   and record how many were dropped** — never cut the top chunk or split a table.
5. Emit a `(context_str, citations)` pair; `citations` maps each tag → metadata + url for the UI.

## Bad example
```python
# BAD: dumps all 30 candidates unlabeled, hard-truncates the string to fit
context = "\n".join(c.text for c in candidates)[:12000]   # slices mid-table, mid-number
prompt = f"Answer using:\n{context}\n\nQ: {q}"            # no citation tags, no source mapping
```

## Good example
```python
def assemble(results, budget_tokens=8000):
    results = dedupe(results)                              # drop near-duplicates
    parts, cites, used = [], {}, 0
    for r in results:                                      # best-first
        tag = f"[{r.ticker} {r.form} {r.fiscal_period or r.filing_date} · {r.section}]"
        block = f"{tag}\n{r.text}\n"
        t = count_tokens(block)
        if used + t > budget_tokens:                      # explicit stop, top chunks kept
            log.info("context budget hit; dropped %d lower-ranked chunks", len(results) - len(parts))
            break
        parts.append(block); cites[tag] = {"url": r.source_url, **r.meta()}; used += t
    return "\n".join(parts), cites
```

## Failure modes seen
- Hard-truncating the concatenated string → cuts a table/number in half; the top chunk loses its tail.
- No citation tags → the model can't cite and the front-end can't link sources.
- Near-duplicate risk-factor boilerplate eats the budget, crowding out the answer-bearing chunk.
- Worst chunk first → the model anchors on a weak passage.

## MUST NOT
- MUST NOT silently truncate — drop lowest-ranked chunks explicitly and log the count.
- MUST NOT split a table or a number across the budget boundary.
- MUST NOT emit context without per-chunk citation tags + source mapping.

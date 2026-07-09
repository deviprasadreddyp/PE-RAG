# Skill: hybrid-retrieval

**Purpose.** Retrieve the chunks most likely to answer the question: metadata pre-filter → dense +
sparse (BM25) search fused with RRF → rerank → top-k. Retrieval quality caps the whole system; if
the right chunk isn't retrieved, no prompt can save the answer.

**When to invoke.** Work in `src/retrieval/retriever.py`.

## How to do it
1. **Metadata pre-filter first** (`skills/metadata-schema`). When the question names a company / form
   / period, build a Chroma `where` clause and search only inside it. Filter, then rank.
2. **Hybrid search.** Dense (Chroma vector search) + sparse (`rank_bm25` over the same filtered set).
   Dense alone misses exact financial vocabulary (ticker symbols, line-item names, "10-Q"); BM25
   catches exact terms. Fuse the two ranked lists with **Reciprocal Rank Fusion (RRF)**.
3. **Over-retrieve then rerank.** Pull ~top-30 candidates, rerank with a cross-encoder / reranker
   (or a cheap `claude-haiku-4-5` scoring pass), keep top-k (~6–10). Do not trust raw top-k.
4. **Fan out for multi-entity questions.** "Compare A, B, C" → retrieve per entity and merge, so one
   company can't crowd out the others.
5. **Determinism.** Same corpus + query ⇒ same results. No wall-clock/randomness on this path.
6. Return `RetrievalResult{chunk, score}` list to `context-assembly`. Measure changes with
   `skills/evaluation` before/after — never tune by vibes.

## Bad example
```python
# BAD: dense-only, no filter, trusts raw top-5 over the whole corpus
hits = collection.query(query_embeddings=[qvec], n_results=5)   # AAPL Q3 question can return TSLA Q1
return hits                                                       # "10-Q" as a term never matched
```

## Good example
```python
def retrieve(query, k=8, pool=30):
    where = build_where(query, ALIASES)                 # metadata pre-filter
    qvec  = embedder.embed_query(query)
    dense = store.query(qvec, n=pool, where=where)      # filtered vector search
    sparse = bm25.search(query, n=pool, where=where)    # filtered BM25
    fused = rrf(dense, sparse, k_const=60)              # reciprocal rank fusion
    ranked = reranker.rerank(query, [f.chunk for f in fused])[:k]
    return ranked
```

## Failure modes seen
- No metadata filter → cross-company / cross-period contamination (Apple question, Tesla chunk).
- Dense-only → misses exact terms (tickers, "diluted EPS", form types).
- Trusting raw top-k without reranking → relevant chunk present but ranked #12, never used.
- Post-filtering after an unfiltered top-k → the top-k is already full of the wrong company.
- Multi-company question retrieved as one blob → one company dominates, others get 0 chunks.

## MUST NOT
- MUST NOT rank over the whole corpus when the query names a company/period — filter first.
- MUST NOT return only dense results for exact-term / financial-vocabulary queries.
- MUST NOT introduce randomness or wall-clock into retrieval.
- MUST NOT claim a retrieval improvement without a metric from `skills/evaluation`.

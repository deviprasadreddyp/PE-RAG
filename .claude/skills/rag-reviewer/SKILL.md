---
name: rag-reviewer
description: Review or design the retrieval side of a RAG system — chunking, metadata, embedding strategy, vector index config, metadata filtering, hybrid (dense+sparse) retrieval, reranking, context assembly, token budgeting, and hallucination risk. Use when building or auditing ingestion/retrieval for The-RAG. Delegates deep chunking decisions to chunking-strategist and measurement to retrieval-evaluator.
---

# RAG Reviewer

Audit the path from raw filing to assembled context. Retrieval quality caps everything
downstream: if the right passage isn't retrieved, no prompt can save the answer.

## When to invoke
- Designing or reviewing ingestion, indexing, retrieval, reranking, or context assembly.
- Diagnosing "the answers are bad" once `root-cause-analyzer` points at retrieval.

## Review dimensions

**Chunking** (→ `chunking-strategist` for the strategy)
- Section-aware, not blind fixed-size. Tables and numbered items kept intact. Sensible size +
  overlap. Each chunk is self-contained enough to be understood alone.

**Metadata** (the highest-leverage lever for SEC RAG)
- Every chunk carries `ticker`, `form` (10-K/10-Q), `filing_date`, `fiscal_period`/`quarter`,
  `cik`, `section`, and `source_url`. Metadata is indexed and filterable.
- Queries pre-filter by metadata *before* vector search when scope is known (company/period).

**Embeddings**
- Model suits financial/long text; consistent model+version for corpus and queries (never mix).
- Normalized vectors; correct distance metric (cosine vs dot). Content-hash cache to avoid
  re-embedding. Dimensionality vs cost vs quality justified (see `tradeoff-analyzer`).

**Index**
- Right structure and params (HNSW `M`/`ef_search`, IVF `nprobe`) for the recall/latency target.
- Metadata filtering is index-backed, not a post-filter that starves top-k.

**Retrieval**
- **Hybrid**: dense + BM25/sparse for exact terms (tickers, line-item names, "10-Q"). Dense
  alone misses exact-match financial vocabulary.
- Query rewriting/expansion where it helps; decomposition for multi-part questions.
- `k` tuned; over-retrieve then rerank rather than trusting raw top-k.

**Reranking**
- Cross-encoder or LLM reranker on the candidate set to fix dense recall/precision gaps.

**Context assembly**
- Fits the token budget; dedupes near-identical chunks; preserves + surfaces citations;
  orders by relevance; doesn't silently truncate the best chunk.

**Hallucination risk**
- Grounded prompt: answer only from context; **cite or refuse**. Include enough context to
  actually answer. Return sources with every answer. (Measure with `retrieval-evaluator`.)

## Output
Findings per dimension with concrete fixes, the highest-leverage change to make first, and any
recommendation to measure the impact with `retrieval-evaluator` before/after.

---
name: performance-optimizer
description: Find and fix performance problems — unnecessary loops, N+1 and repeated DB/vector queries, repeated embeddings or LLM calls, missing caching or batching, blocking I/O, and inefficient data structures. Use when latency, throughput, or resource use matters, or when reviewing hot paths in ingestion and retrieval. Measure before and after; optimize the actual bottleneck.
---

# Performance Optimizer

Make it fast where speed matters — after it's correct. **Measure first**: optimizing an
unprofiled guess wastes effort and adds complexity.

## When to invoke
- Latency/throughput/cost targets are at risk.
- Reviewing hot paths: ingestion at corpus scale, per-query retrieval, generation.

## Method
1. **Measure.** Profile or time the real workload. Identify the dominant cost. Don't optimize
   what isn't the bottleneck.
2. **Attack the biggest cost first.** Algorithmic and I/O wins dwarf micro-optimizations.
3. **Re-measure** after each change. Keep changes that help; revert those that don't.

## What to look for

**Redundant work**
- Repeated computation inside loops that could be hoisted.
- Re-embedding the same text; re-calling the LLM for identical prompts. → cache.
- N+1 queries (one query per item in a loop). → batch/join.

**Batching**
- Embed in batches, not one call per chunk. Upsert to the vector store in bulk.
- Batch LLM calls where the API and latency budget allow.

**Caching** (coordinate with `cost-optimizer`)
- Cache embeddings keyed by content hash. Cache retrieval results / final answers for repeat
  queries. Use prompt caching for stable system/context prefixes.
- Be explicit about invalidation — stale cache on a changed corpus is a correctness bug.

**I/O & concurrency**
- Don't block on network serially when calls are independent — parallelize (async/threads).
- Stream large files instead of loading whole filings into memory when possible.
- Reuse HTTP clients / connection pools; don't reconnect per call.

**Data structures & indexing**
- Right structure for the access pattern (set membership vs list scan; dict lookup vs linear).
- Vector index tuned (HNSW `ef`/`M`, IVF `nprobe`) for the recall/latency tradeoff you need.
- Metadata filters use indexes, not full scans.

**Memory**
- Avoid materializing the whole corpus at once; stream/iterate. Watch for accidental O(n²).

## Guardrails
- Don't sacrifice correctness or readability for speed the workload doesn't need.
- Record the measured before/after so the win is real, not assumed.

## Output
The bottleneck (with numbers), the change, and the measured improvement. If a proposed
optimization isn't worth the complexity, say so.

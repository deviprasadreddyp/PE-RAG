---
name: cost-optimizer
description: Reduce the money and token cost of an LLM/RAG system — repeated LLM calls, repeated embeddings, oversized prompts and context, unnecessary model tier, missing caching, and un-batched API calls. Use when reviewing spend, before scaling to the full corpus, or when a design makes avoidable paid calls. Never trade away correctness or required quality for cost.
---

# Cost Optimizer

Every embedding and LLM call costs money and tokens. Cut waste, not quality. Estimate the cost
of a design at corpus/traffic scale *before* running it — a naive full-corpus ingest can be a
surprise bill.

## When to invoke
- Reviewing/estimating spend; before scaling ingestion to all 247 filings (and future ones).
- A design makes repeated or oversized paid calls.

## Where the money goes (attack in order of impact)

**Repeated embeddings**
- Cache embeddings keyed by a content hash. Never re-embed unchanged text on re-ingest.
- Deduplicate near-identical chunks before embedding (overlap regions, boilerplate).

**Repeated LLM calls**
- Cache answers/reranks for identical (query, context) pairs. Deduplicate in-flight identical calls.
- Don't call the model to do what code can do (parsing, filtering, formatting).

**Oversized prompts & context**
- Retrieve/keep only the chunks you need; trim boilerplate; don't stuff top-k "just in case."
- Compress or summarize context only when it doesn't drop load-bearing numbers.
- Use **prompt caching** for stable system prompts and reused context prefixes.

**Model tier**
- Match model to task: a cheaper/faster model for reranking, classification, query rewriting, and
  extraction; the strong model for the final grounded answer. (See `claude-api` for current tiers
  and prices — Opus 4.8 / Sonnet 5 / Haiku 4.5.) Don't pay Opus prices for a routing decision.

**Batching**
- Batch embeddings and, where possible, generation. Bulk-upsert to the vector store.

## Method
1. **Estimate** tokens × calls × price for ingestion and per-query, at target scale. Write the number.
2. Find the dominant cost. Attack it first (usually context size × request volume, or a full
   re-embed).
3. Apply caching/batching/right-sizing. Re-estimate.
4. Confirm quality held via `retrieval-evaluator` — a cost win that tanks recall/faithfulness is a loss.

## Guardrails
- Correctness and required accuracy are non-negotiable. For finance, refusing beats a cheap wrong
  number. Coordinate caching invalidation with `performance-optimizer` so stale ≠ wrong.

## Output
A cost breakdown (before), the changes, the projected cost (after), and a check that quality
metrics are unchanged.

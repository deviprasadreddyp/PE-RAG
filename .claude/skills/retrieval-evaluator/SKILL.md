---
name: retrieval-evaluator
description: Measure RAG quality with real metrics instead of vibes — build a labeled query set and evaluate retrieval (recall@k, precision@k, MRR, nDCG, hit rate) and generation (faithfulness/groundedness, answer relevance, citation accuracy, numeric correctness). Use to compare chunking/embedding/retrieval configs, to set a baseline before changes, and to prove an improvement is real.
---

# Retrieval Evaluator

You can't improve what you don't measure. Every chunking, embedding, or retrieval change should
be justified by a number on a fixed evaluation set — not by how one example looks.

## When to invoke
- Establishing a baseline before tuning.
- Comparing two configs (chunk size, embedding model, hybrid on/off, reranker on/off, k).
- Before claiming a change "improved retrieval."

## Build the eval set first
- 30–100+ hand-labeled questions spanning the real query types: single-company lookup,
  cross-company comparison, cross-period trend, definitional, numeric ("what was revenue…").
- For each: the expected supporting chunk(s)/filing(section) and the expected answer facts
  (exact figures, units, period). This is your ground truth; version it.
- Include hard negatives: questions the corpus can't answer (should trigger a refusal).

## Retrieval metrics
- **Recall@k** — is the correct chunk in the top-k? (The single most important RAG metric —
  it's the ceiling on answer quality.)
- **Precision@k** / **MRR** — how high is the right chunk ranked? Rank quality for the reranker.
- **nDCG** — graded relevance across the ranked list.
- **Hit rate** — fraction of queries with ≥1 relevant chunk retrieved.
- Report per query-type, not just an average — averages hide that comparisons fail while lookups pass.

## Generation / answer metrics
- **Faithfulness / groundedness** — every claim in the answer is supported by retrieved context
  (no hallucination). Can be judged by an LLM-as-judge with the context + answer.
- **Answer relevance** — does it actually address the question?
- **Citation accuracy** — do cited sources contain the claimed facts, at the right period/company?
- **Numeric correctness** — figures/units/periods match the source verbatim (critical for finance).
- **Refusal correctness** — unanswerable questions get "I don't know," not invention.

## Method
1. Freeze the eval set. 2. Run config A, record metrics. 3. Change ONE variable. 4. Re-run,
compare. 5. Keep changes that move the metric that matters; log regressions on others.
Watch for overfitting to the eval set — refresh it periodically.

## Output
A metrics table (config × metric, broken out by query type), the winning config, and an honest
note on what regressed or where the eval set is thin. Numbers, not adjectives.

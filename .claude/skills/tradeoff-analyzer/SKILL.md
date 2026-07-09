---
name: tradeoff-analyzer
description: Compare options before committing to a database, framework, library, algorithm, model, or architecture. Evaluate each on pros, cons, scalability, maintainability, cost, complexity, and fit to the actual requirements — then make a clear recommendation. Use whenever a decision has more than one reasonable answer and reversing it later would be expensive.
---

# Tradeoff Analyzer

Make consequential technical decisions deliberately. The output is a **recommendation with
reasons**, not a neutral survey — but the reasons must be honest about what you're giving up.

## When to invoke
- Choosing a vector DB, embedding model, LLM, framework, storage engine, or algorithm.
- Any architectural fork where reversal is costly.

## Method
1. **State the decision and the constraints.** What are we choosing, and what must the choice
   satisfy? Pull the non-functional requirements (latency, cost, scale, team skills) forward.
2. **List 2–4 real candidates.** Include the boring/default option and "do nothing."
3. **Score each against dimensions that matter here** (not a generic list):
   - Fit to requirements · Performance/scalability · Cost (money + tokens) · Maintainability &
     operational burden · Complexity · Ecosystem/maturity · Lock-in & exit cost · Team familiarity.
4. **Name the decisive factors.** Usually 1–2 dimensions actually decide it; say which.
5. **Recommend one**, state the top reason, and state the main risk you're accepting.
6. **Note the reversal cost** and what evidence would make you switch later.

## Format
A compact comparison table (candidates × dimensions), then: **Recommendation**, **Why**,
**What we're trading away**, **When to revisit**.

## Example dimensions for The-RAG decisions
- **Vector store** (pgvector vs Qdrant vs Chroma vs FAISS): ops burden, metadata filtering
  power, hybrid search support, scale ceiling, cost, local-dev ergonomics.
- **Embedding model**: quality on financial text, dimensionality/cost, context length, latency,
  self-host vs API.
- **Chunking approach**: recall vs precision vs cost — see `chunking-strategist`.

## Guardrails
- Don't invent differences; if two options are equivalent on a dimension, say so.
- Prefer the simplest option that meets requirements (`complexity-minimizer`); novelty is a cost.
- Weight dimensions by *this* project's reality, not general best practice.

# Evaluation Framework

Evaluation is a **first-class part of the system**, not a manual afterthought. The framework answers
four questions — and, critically, lets us answer *"if I change chunking / top-k / prompt / reranker
tomorrow, did the system get better or worse?"* objectively.

1. **Did retrieval find the right evidence?** — retrieval metrics vs a golden set
2. **Did the LLM answer correctly and relevantly?** — RAGAS answer_relevancy
3. **Is every claim grounded in the retrieved evidence?** — RAGAS faithfulness + our citation checks
4. **Can we measure regressions continuously?** — report diff vs the previous run

## Deliberately small metric set

Each metric maps to one engineering decision — a focused set beats a wall of scores.

| Layer | Metric | Question it answers → decision |
|-------|--------|-------------------------------|
| Retrieval | **Recall@k** (pooled) | Did we retrieve the relevant chunks? → embeddings / hybrid / top-k |
| Retrieval | **Precision@k** | Is the context clean (not padded with junk)? → filters / rerank / k |
| Retrieval | **MRR** | Is the best hit near the top? → ranking / rerank |
| Retrieval | **NDCG@k** | Overall rank quality → fusion / rerank |
| Retrieval | **company_recall** | For comparisons, did we cover every requested company? → per-entity planning |
| Generation | **Faithfulness** (RAGAS) | Is the answer grounded (no hallucination)? → prompt / guardrails |
| Generation | **Answer Relevancy** (RAGAS) | Did it answer the question? → prompt |
| Generation | **Context Precision** (RAGAS) | Were retrieved chunks actually useful? → retrieval / k |
| Generation | **Context Recall** (RAGAS) | Was enough evidence retrieved? → retrieval / k |
| Generation | **citation groundedness / coverage** | Deterministic grounding check (no LLM) → complements faithfulness |

## Layers (`src/eval/`)

| Module | Role |
|--------|------|
| `datasets/golden.jsonl` | 25 curated business questions with metadata ground truth (companies/years/forms/sections) + 2 out-of-corpus refusal cases |
| `relevance.py` | relevance judgment by exact `expected_chunk_ids` OR metadata; recall proxies |
| `metrics.py` | pure ranking + citation metrics (Recall@k, Precision@k, MRR, NDCG@k, groundedness, coverage) |
| `retrieval_eval.py` | **A/B**: bm25 vs vector vs hybrid vs hybrid+rerank, scored per variant (pooled recall) |
| `ragas_runner.py` | **RAGAS** generation metrics (grader LLM = OpenRouter model, embeddings = local bge) |
| `tracing.py` | **LangSmith** tracing toggle (traces, tokens, latency) — on when `LANGSMITH_API_KEY` is set |
| `report.py` | JSON + self-contained HTML report + **regression** diff vs the previous run |
| `run_eval.py` | orchestrator: per-case + A/B + optional RAGAS → one report, compared to previous |
| `dashboard.py` | Streamlit dashboard over the report (overview, A/B chart, RAGAS, per-case) |

## Ground truth (why metadata, not chunk ids)

The corpus has ~32K chunks; hand-labeling relevant chunk ids per question doesn't scale. So the
golden set expresses relevance as **metadata expectations** (a chunk is relevant if its
ticker/year/form/section match) — which is exactly how an analyst judges "is this the right
evidence?". Exact `expected_chunk_ids` are also supported if you annotate them. Recall@k in the A/B
harness uses **pooled relevance** (union of relevant found by any strategy) as the denominator — a
standard IR trick when full labels are absent — so strategies stay comparable.

## Running it

```bash
# offline eval over the golden set (needs the built index; RAGAS + key optional)
python -m src.eval.run_eval

# with RAGAS generation grading (needs: pip install ragas langchain-huggingface + OPENROUTER_API_KEY)
python -c "from src.eval.run_eval import run_eval; run_eval(run_ragas_eval=True)"

# view results
open data/logs/eval_report.html          # or: streamlit run src/eval/dashboard.py
```

Outputs: `data/logs/eval_report.json` + `eval_report.html`. Re-running compares against the previous
report and records **regressions** (any metric down > 0.02) and improvements.

## What this demonstrates

> "I made evaluation a first-class component. Retrieval is evaluated independently with Recall@k,
> Precision@k, MRR, and NDCG against a curated golden set, and an A/B harness proves hybrid + reranking
> beat vector- or BM25-only *with numbers*. Generation is graded with RAGAS (faithfulness,
> answer_relevancy, context precision/recall), and LangSmith traces every call. A dashboard and a
> regression check mean any change to chunking, retrieval, reranking, or prompting is measured — not
> guessed."

## Deferred (needs resources, not code)

- **Live run** needs the built index (`python -m src.run --stage all`) — local, no key.
- **RAGAS** needs `pip install ragas langchain-huggingface` + `OPENROUTER_API_KEY` (grader LLM).
- **LangSmith** needs `LANGSMITH_API_KEY` in `.env` (else tracing is a silent no-op).

All metric/report/regression logic is pure and unit-tested; only the live grading is gated.

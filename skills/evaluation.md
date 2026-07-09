# Skill: evaluation

**Purpose.** Measure retrieval and answer quality with real numbers, not vibes. Every chunking /
embedding / retrieval / prompt change must be justified by a metric on a fixed set. This is also the
"how you evaluated quality" deliverable.

**When to invoke.** Work in `sec_rag/eval/`; before claiming any change improved the system.

## How to do it
1. **Build a labeled eval set first** (`sec_rag/eval/eval_set.jsonl`): 20–50+ questions spanning the
   real query types — single-company lookup, cross-company comparison, cross-period trend, sector,
   and **unanswerable** (must refuse). For each: the expected supporting filing(s)/section and the
   expected answer facts (exact figures + units + period). Version it.
2. **Retrieval metrics:**
   - **recall@k** — is the correct chunk in the top-k? (the ceiling on answer quality — the most
     important metric).
   - **MRR / precision@k** — how highly is it ranked (reranker quality).
   - Report **per query-type**, not just an average — averages hide that comparisons fail.
3. **Answer metrics:**
   - **faithfulness** — every claim supported by the retrieved context (LLM-as-judge with context +
     answer).
   - **numeric correctness** — figures/units/periods match the source verbatim.
   - **citation accuracy** — cited tags actually contain the claimed fact, right company/period.
   - **refusal correctness** — unanswerable questions get a refusal, not an invention.
4. **Method:** freeze the set → run config A → change ONE variable → re-run → compare. Keep changes
   that move the metric that matters; log regressions. Watch for overfitting to the eval set.

## Bad example
```python
# BAD: "looks good" on one hand-picked question, no ground truth, no per-type breakdown
res = answer("What is Apple's revenue?")
print(res.answer)          # eyeballed once, declared "working"
```

## Good example
```python
def evaluate(cfg):
    rows = [json.loads(l) for l in open("sec_rag/eval/eval_set.jsonl")]
    by_type = defaultdict(lambda: {"recall": [], "faithful": [], "numeric": [], "refusal": []})
    for r in rows:
        hits = retrieve(r["question"])
        by_type[r["type"]]["recall"].append(recall_at_k(hits, r["gold_chunks"], k=8))
        if r["type"] == "unanswerable":
            by_type[r["type"]]["refusal"].append(is_refusal(answer(r["question"]).answer))
        else:
            a = answer(r["question"])
            by_type[r["type"]]["faithful"].append(judge_faithfulness(a, hits))
            by_type[r["type"]]["numeric"].append(numeric_match(a, r["gold_facts"]))
    return summarize(by_type)          # table: metric × query-type
```

## Failure modes seen
- Evaluating on one anecdote instead of a labeled set → improvements are imaginary.
- Reporting only the average → cross-company comparison quietly fails while lookups pass.
- No unanswerable cases → the system's tendency to hallucinate never gets caught.
- Changing several variables at once → can't attribute the metric change.

## MUST NOT
- MUST NOT claim "it works" / "it improved" without a number from the eval set.
- MUST NOT omit unanswerable (refusal) cases from the eval set.
- MUST NOT report only a global average — break out by query type.

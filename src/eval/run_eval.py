"""Retrieval eval harness — score the pipeline over the golden set (src/eval/eval_set.jsonl).

Relevance is judged by METADATA (no hand-labeled chunk ids needed for this closed corpus): a
retrieved chunk is relevant if its ticker / year / section match the case's expectations. From the
final evidence ranking we compute precision@k, MRR, NDCG@k, hit@k, a company-recall proxy, and the
answer's citation groundedness/coverage; ``expect_refusal`` cases score on whether we correctly
refused.

``evaluate_case`` and ``aggregate`` are pure and unit-tested. ``run_eval`` executes the real
pipeline per query (needs the built index + keys — deferred, like the embed/store runs) and writes
``data/logs/eval_report.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.config import settings
from src.eval import metrics, relevance

_EVAL_SET = Path(__file__).parent / "datasets" / "golden.jsonl"


def load_eval_set(path: str | Path | None = None) -> list[dict]:
    p = Path(path) if path is not None else _EVAL_SET
    return [json.loads(ln) for ln in p.read_text("utf-8").splitlines() if ln.strip()]


# re-exported for callers/tests that used run_eval.is_relevant
is_relevant = relevance.is_relevant


def evaluate_case(result, expected: dict, *, k: int | None = None) -> dict:
    """Score one PipelineResult against its expected metadata (or expected refusal)."""
    k = k or settings.rerank_top_k

    if expected.get("expect_refusal"):
        return {"refused": result.refused, "refusal_correct": float(result.refused)}

    evidence = result.evidence or []
    chunks = [e.chunk for e in evidence]
    flags = relevance.relevance_flags(chunks, expected)
    evidence_ids = [e.evidence_id for e in evidence]
    cited_ids = [e.evidence_id for e in _cited_evidence(result)]

    return {
        "refused": result.refused,
        "precision@k": metrics.precision_at_k(flags, k),
        "hit@k": metrics.hit_at_k(flags, k),
        "mrr": metrics.reciprocal_rank(flags),
        "ndcg@k": metrics.ndcg_at_k(flags, k),
        "company_recall": relevance.company_recall(chunks, expected),
        "citation_groundedness": metrics.citation_groundedness(cited_ids, evidence_ids),
        "citation_coverage": metrics.citation_coverage(cited_ids, evidence_ids),
    }


def _cited_evidence(result) -> list:
    """Evidence blocks whose citation tag appears in the answer's sources (best-effort mapping)."""
    tags = {c.tag for c in result.answer.sources}
    return [e for e in (result.evidence or []) if e.tag in tags]


def aggregate(rows: list[dict]) -> dict:
    """Mean of each numeric metric across cases (keys present in a row)."""
    if not rows:
        return {}
    keys: list[str] = []
    for r in rows:
        for key in r:
            if isinstance(r[key], (int, float)) and not isinstance(r[key], bool) and key not in keys:
                keys.append(key)
    out = {}
    for key in keys:
        vals = [r[key] for r in rows if key in r and isinstance(r[key], (int, float))
                and not isinstance(r[key], bool)]
        out[key] = round(sum(vals) / len(vals), 4) if vals else 0.0
    out["n_cases"] = len(rows)
    return out


def run_eval(*, path=None, out=None, k=None, **components) -> dict:
    """Run the pipeline over the golden set and return {cases, summary}; writes a JSON report."""
    from src.retrieval.retrieval_pipeline import answer_query  # local import (needs components)

    cases = load_eval_set(path)
    rows = []
    for case in cases:
        result = answer_query(case["question"], **components)
        rows.append({"question": case["question"], **evaluate_case(result, case, k=k)})
    report = {"cases": rows, "summary": aggregate(rows)}
    out_path = Path(out) if out is not None else settings.data_path / "logs" / "eval_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    try:
        r = run_eval()
    except (ImportError, RuntimeError, FileNotFoundError) as exc:
        print(f"Eval: cannot run yet ({type(exc).__name__}: {exc}). "
              "Build the index (embed + store) and set keys first.")
    else:
        print("Eval summary:", json.dumps(r["summary"], indent=2))

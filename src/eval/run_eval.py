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


_RETRIEVAL_KEYS = ("store", "index", "embedder", "reranker")


def _default_retrieval_components(components: dict) -> dict:
    """Fill missing retrieval components for the A/B harness and live eval path."""
    out = dict(components)
    if "store" not in out:
        from src.pipeline.store import ChromaVectorStore
        out["store"] = ChromaVectorStore()
    if "index" not in out:
        from src.pipeline.store import Bm25Index, _vectorstore_dir
        out["index"] = Bm25Index.load(_vectorstore_dir() / "bm25.json")
    if "embedder" not in out:
        from src.pipeline.embed import get_embedder
        out["embedder"] = get_embedder()
    if "reranker" not in out:
        from src.retrieval.reranker import get_reranker
        out["reranker"] = get_reranker()
    return out


def assemble_report(rows: list[dict], *, ab: dict | None = None, ragas: dict | None = None) -> dict:
    """Combine per-case generation-path rows + optional A/B + RAGAS into one report (pure)."""
    return {"retrieval": {"cases": rows, "summary": aggregate(rows)}, "ab": ab, "ragas": ragas}


def run_eval(*, path=None, out_dir=None, k=None, run_ab=True, run_ragas_eval=False,
             ragas_evaluator=None, **components) -> dict:
    """Full evaluation: per-case generation path + retrieval A/B (+ optional RAGAS) → JSON+HTML report.

    Compares against the previous run and records regressions. Needs the built index + keys (deferred,
    like the embed/store runs); the report-building pieces are pure and unit-tested.
    """
    from src.retrieval.retrieval_pipeline import answer_query
    from src.eval import ragas_runner, report as report_mod, retrieval_eval, tracing

    tracing.enable_langsmith()                                   # trace the answer calls if a key is set
    cases = load_eval_set(path)
    ret_components = _default_retrieval_components(
        {k2: v for k2, v in components.items() if k2 in _RETRIEVAL_KEYS}
    )
    components = {**components, **ret_components}

    rows, ragas_rows = [], []
    for case in cases:
        result = answer_query(case["question"], **components)
        rows.append({"id": case.get("id"), "question": case["question"], **evaluate_case(result, case, k=k)})
        if not case.get("expect_refusal") and not result.refused:
            ragas_rows.append({"question": case["question"], "answer": result.answer.answer,
                               "contexts": [e.chunk.text for e in (result.evidence or [])]})

    ab = retrieval_eval.ab_eval(cases, k=k, **ret_components) if run_ab else None
    ragas = (ragas_runner.run_ragas(ragas_runner.build_samples(ragas_rows), evaluator=ragas_evaluator)
             if run_ragas_eval and ragas_rows else None)

    report = assemble_report(rows, ab=ab, ragas=ragas)
    out_dir = Path(out_dir) if out_dir is not None else settings.data_path / "logs"
    previous = report_mod.load_previous(out_dir)
    if previous:
        report["regression"] = report_mod.compare_to_previous(
            report_mod.flat_summary(report), report_mod.flat_summary(previous))
    report["paths"] = report_mod.write_reports(report, out_dir)
    return report


if __name__ == "__main__":
    try:
        r = run_eval()
    except (ImportError, RuntimeError, FileNotFoundError) as exc:
        print(f"Eval: cannot run yet ({type(exc).__name__}: {exc}). "
              "Build the index (embed + store) and set OPENAI_API_KEY first.")
    else:
        print("Retrieval summary:", json.dumps(r["retrieval"]["summary"], indent=2))
        if r.get("ab"):
            print("A/B summary:", json.dumps(r["ab"]["summary"], indent=2))
        print("Report written to:", r["paths"]["html"])

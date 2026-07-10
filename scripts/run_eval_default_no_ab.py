"""Run the full golden eval through the default RAG path, without retrieval A/B.

This intentionally keeps the real cross-encoder reranker enabled, but reuses one
reranker instance across cases so the run reflects warm service behavior instead
of repeatedly paying model cold-start cost. It writes per-case checkpoints and
the dashboard report at ``data/logs/eval_report.json``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import settings
from src.eval import report as report_mod
from src.eval.run_eval import assemble_report, evaluate_case, load_eval_set
from src.pipeline.embed import get_embedder
from src.pipeline.store import Bm25Index, ChromaVectorStore, _vectorstore_dir
from src.retrieval.reranker import get_reranker
from src.retrieval.retrieval_pipeline import answer_query


def main() -> None:
    cases = load_eval_set()
    out_dir = settings.data_path / "logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = out_dir / "eval_default_no_ab_checkpoint.json"

    print(f"cases={len(cases)}")
    print("mode=default_pipeline_hybrid_plus_real_reranker")
    print("ab_tests=disabled")
    print(f"generation_model={settings.generation_model}")
    print(f"embedding_model={settings.embedding_model}")
    print(f"rerank_model={settings.rerank_model}")

    store = ChromaVectorStore()
    index = Bm25Index.load(_vectorstore_dir() / "bm25.json")
    embedder = get_embedder()

    print("loading_reranker=true", flush=True)
    reranker_start = time.perf_counter()
    reranker = get_reranker()
    print(
        f"loading_reranker_done_s={time.perf_counter() - reranker_start:.2f} "
        f"class={type(reranker).__name__}",
        flush=True,
    )

    rows: list[dict] = []
    started = time.perf_counter()
    for i, case in enumerate(cases, start=1):
        case_start = time.perf_counter()
        print(f"case_start={i}/{len(cases)} id={case.get('id')}", flush=True)
        result = answer_query(
            case["question"],
            store=store,
            index=index,
            embedder=embedder,
            reranker=reranker,
        )
        row = {
            "id": case.get("id"),
            "question": case["question"],
            **evaluate_case(result, case),
            "latency_s": round(time.perf_counter() - case_start, 3),
        }
        rows.append(row)
        checkpoint.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(
            "case_done="
            f"{i}/{len(cases)} id={case.get('id')} refused={row.get('refused')} "
            f"hit={row.get('hit@k', '')} mrr={row.get('mrr', '')} "
            f"latency_s={row['latency_s']}",
            flush=True,
        )

    report = assemble_report(rows, ab=None, ragas=None)
    previous = report_mod.load_previous(out_dir)
    if previous:
        report["regression"] = report_mod.compare_to_previous(
            report_mod.flat_summary(report),
            report_mod.flat_summary(previous),
        )
    report["run"] = {
        "mode": "default_pipeline_no_ab",
        "ab_tests": False,
        "reranker": type(reranker).__name__,
        "rerank_model": settings.rerank_model,
        "generation_model": settings.generation_model,
        "embedding_model": settings.embedding_model,
        "total_latency_s": round(time.perf_counter() - started, 3),
    }
    report["paths"] = report_mod.write_reports(report, out_dir)

    print("retrieval_summary=", json.dumps(report["retrieval"]["summary"], indent=2))
    print("ab_summary=null")
    print("run=", json.dumps(report["run"], indent=2))
    print("paths=", json.dumps(report["paths"], indent=2))


if __name__ == "__main__":
    main()

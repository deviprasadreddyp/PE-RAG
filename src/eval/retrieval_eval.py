"""Retrieval A/B evaluation — justify Hybrid + reranking WITH evidence (no LLM).

For each golden question we run four retrieval variants and score each against the case's ground
truth, so we can answer "does hybrid actually beat vector/BM25?" and "does the reranker help?":

    bm25  ·  vector  ·  hybrid (RRF)  ·  hybrid+rerank

Metrics per variant: Recall@k, Precision@k, MRR, NDCG@k. Recall uses POOLED relevance (the union of
relevant chunks found by ANY variant) as the denominator — a standard IR trick when full labels are
absent — so the variants are directly comparable. Deterministic given the index; testable with fakes.
"""

from __future__ import annotations

from src.config import settings
from src.eval import metrics, relevance
from src.retrieval import (
    bm25_retriever, hybrid_fusion, metadata_filter, metadata_parser,
    reranker as rerank_mod, vector_retriever,
)

MODES = ("bm25", "vector", "hybrid", "hybrid+rerank")


def retrieval_variants(question: str, *, store, index, embedder, reranker=None,
                       vector_k: int | None = None, bm25_k: int | None = None) -> dict[str, list]:
    """Run the four retrieval variants for one question → {mode: ranked RetrievalResult list}."""
    qa = metadata_parser.parse_query(question)
    hf = metadata_filter.build_filter(qa)
    vec = vector_retriever.search(question, hf, embedder=embedder, store=store,
                                  k=vector_k or settings.vector_top_k)
    bm = bm25_retriever.search(question, hf, index=index, k=bm25_k or settings.bm25_top_k)
    hybrid = hybrid_fusion.reciprocal_rank_fusion(vec, bm)
    if store is not None:
        vector_retriever.hydrate_texts(hybrid, store)
    reranked = rerank_mod.rerank(question, hybrid, reranker=reranker, top_k=len(hybrid))
    return {"bm25": bm, "vector": vec, "hybrid": hybrid, "hybrid+rerank": reranked}


def score_variants(variants: dict[str, list], expected: dict, *, k: int | None = None) -> dict:
    """Score each variant (Recall@k pooled, Precision@k, MRR, NDCG@k) against ground truth."""
    k = k or settings.rerank_top_k
    pooled = {r.chunk.id for results in variants.values() for r in results
              if relevance.is_relevant(r.chunk, expected)}
    out: dict[str, dict] = {}
    for mode, results in variants.items():
        flags = relevance.relevance_flags([r.chunk for r in results], expected)
        out[mode] = {
            "recall@k": relevance.pooled_recall_at_k(flags, len(pooled), k),
            "precision@k": metrics.precision_at_k(flags, k),
            "mrr": metrics.reciprocal_rank(flags),
            "ndcg@k": metrics.ndcg_at_k(flags, k),
        }
    return out


def _aggregate_modes(per_case: list[dict]) -> dict:
    """Mean each metric per mode across cases."""
    buckets: dict[str, list[dict]] = {}
    for row in per_case:
        for mode, m in row["scores"].items():
            buckets.setdefault(mode, []).append(m)
    return {
        mode: {metric: round(sum(r[metric] for r in rows) / len(rows), 4) for metric in rows[0]}
        for mode, rows in buckets.items()
    }


def ab_eval(cases: list[dict], *, k: int | None = None, **components) -> dict:
    """Run the A/B over the golden set (skipping refusal cases) → {per_case, summary}."""
    per_case = []
    for case in cases:
        if case.get("expect_refusal"):
            continue                                    # A/B measures retrieval quality only
        variants = retrieval_variants(case["question"], **components)
        per_case.append({"id": case.get("id"), "scores": score_variants(variants, case, k=k)})
    return {"per_case": per_case, "summary": _aggregate_modes(per_case)}

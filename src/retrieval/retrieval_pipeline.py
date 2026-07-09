"""Stage orchestrator — validate → understand → plan → hybrid search → RRF → rerank → dedup
→ evidence → guardrails → prompt → [ONE LLM CALL] → parse → cite.

Everything is deterministic or local ML up to the single Claude call, which is made ONLY when
guardrails pass. Implements the failure/fallback matrix (RETRIEVAL_DESIGN.md §9): a retriever that
errors degrades to the other; if both yield nothing, or guardrails reject, we return a grounded
refusal and make **zero** LLM calls.

Components (store / index / embedder / reranker / generator) are injectable — tests pass fakes, so
the whole pipeline runs with no network or keys. Real defaults are constructed lazily and guarded.
Returns a ``PipelineResult`` carrying the Answer plus a stage trace for logging (P18) and the
debug UI (P19/P20).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from src.config import settings
from src.generation import generate as gen_mod
from src.retrieval import (
    bm25_retriever, deduplicator, evidence_builder, guardrails, hybrid_fusion,
    metadata_filter, metadata_parser, prompt_builder, query_log, query_validator,
    reranker as rerank_mod, response_parser, retrieval_planner, vector_retriever,
)
from src.schemas import Answer, Evidence, GuardrailResult, QueryAnalysis, RetrievalResult


@dataclass
class PipelineResult:
    answer: Answer
    analysis: QueryAnalysis | None = None
    guardrail: GuardrailResult | None = None
    evidence: list[Evidence] = field(default_factory=list)
    refused: bool = False
    trace: dict = field(default_factory=dict)


def _try(fn, trace: dict, key: str, default=None):
    """Run fn(); on any error record it in the trace and return default (graceful degradation)."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — degradation is intentional; the error is recorded
        trace[key] = repr(exc)
        return default


def _default_store():
    from src.pipeline.store import ChromaVectorStore
    return ChromaVectorStore()


def _default_index():
    from src.pipeline.store import Bm25Index, _vectorstore_dir
    return Bm25Index.load(_vectorstore_dir() / "bm25.json")


def _default_embedder():
    from src.pipeline.embed import OpenAIEmbedder
    return OpenAIEmbedder()


def answer_query(query: str, *, store=None, index=None, embedder=None, reranker=None,
                 generator=None) -> PipelineResult:
    # Stage 1 — validation
    try:
        q = query_validator.validate_query(query)
    except query_validator.QueryError as exc:
        return PipelineResult(answer=response_parser.refusal_answer(f"Invalid query: {exc}"),
                              refused=True, trace={"stage": "validation", "error": str(exc)})

    # Stages 2-5 — understand, filter, plan (all deterministic)
    qa = metadata_parser.parse_query(q)
    hard = metadata_filter.build_filter(qa)
    plan = retrieval_planner.plan_retrieval(qa)
    trace: dict = {
        "query": q, "intents": qa.intents, "companies": qa.companies,
        "years": qa.years, "filter": metadata_filter.describe(hard),
        "plan": plan.mode, "section_boosts": plan.section_boosts,
    }

    # resolve components (lazy, guarded)
    store = store or _try(_default_store, trace, "store_error")
    index = index or _try(_default_index, trace, "index_error")
    embedder = embedder or _try(_default_embedder, trace, "embedder_error")

    # Stage 6 — hybrid retrieval with fallback (§9)
    vec = _try(lambda: vector_retriever.search(q, hard, embedder=embedder, store=store,
                                               k=settings.vector_top_k),
               trace, "vector_error", default=[]) if embedder and store else []
    bm = _try(lambda: bm25_retriever.search(q, hard, index=index, k=settings.bm25_top_k),
              trace, "bm25_error", default=[]) if index else []
    trace["vector_ids"] = [r.chunk.id for r in vec]
    trace["bm25_ids"] = [r.chunk.id for r in bm]
    if not vec and not bm:
        return PipelineResult(
            answer=response_parser.refusal_answer("No relevant evidence was retrieved."),
            analysis=qa, refused=True, trace=trace)

    # Stage 7 — RRF fusion
    fused = hybrid_fusion.reciprocal_rank_fusion(
        vec, bm, top_n=plan.pool_size or settings.candidate_pool)
    trace["rrf_ids"] = [r.chunk.id for r in fused]
    if store is not None:                                     # hydrate BM25-only texts for reranking
        _try(lambda: vector_retriever.hydrate_texts(fused, store), trace, "hydrate_error")

    # Stage 8 — rerank (skip-on-fail handled inside rerank_mod.rerank)
    reranked = rerank_mod.rerank(q, fused, reranker=reranker, top_k=len(fused))
    trace["reranked_ids"] = [r.chunk.id for r in reranked]

    # Stage 9 — dedup, Stages 10-11 — evidence
    evidence = evidence_builder.build_evidence(deduplicator.deduplicate(reranked))
    trace["evidence_ids"] = [e.chunk.id for e in evidence]

    # Stage 12 — guardrails (top_similarity from the vector cosine; neutral if vector was down)
    top_sim = max((r.score for r in vec), default=settings.min_similarity)
    gr = guardrails.evaluate(qa, evidence, top_similarity=top_sim)
    trace["guardrail"] = {"ok": gr.ok, "action": gr.action, "reason": gr.reason,
                          "confidence": gr.confidence}
    if not gr.ok:                                             # refuse — ZERO LLM calls
        return PipelineResult(answer=response_parser.refusal_answer(gr.reason), analysis=qa,
                              guardrail=gr, evidence=evidence, refused=True, trace=trace)

    # Stage 13 — prompt (budget-fit)
    kept = prompt_builder.fit_to_budget(evidence, qa.query)
    prompt = prompt_builder.build_prompt(qa, kept)
    trace["prompt_version"] = prompt.prompt_version
    trace["evidence_used"] = [e.evidence_id for e in kept]

    # Stage 14 — THE single LLM call
    body = gen_mod.generate(prompt, generator=generator)
    body.confidence = gr.confidence                          # deterministic confidence is authoritative

    # Stages 15-16 — parse + citations
    retrieved = [RetrievalResult(chunk=e.chunk, score=e.score) for e in kept]
    answer = response_parser.build_answer(body, kept, retrieved=retrieved, usage={})
    return PipelineResult(answer=answer, analysis=qa, guardrail=gr, evidence=kept, trace=trace)


def run_query(query: str, *, log: bool = True, base=None, **kwargs) -> PipelineResult:
    """Timed wrapper around ``answer_query`` that also writes a query log (Stage 17)."""
    start = time.perf_counter()
    result = answer_query(query, **kwargs)
    latency = time.perf_counter() - start
    if log:
        record = query_log.build_log_record(result, latency_s=latency,
                                             usage=result.answer.usage if result.answer else {})
        query_log.write_log(record, base=base)
    return result

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

import re
import time
from collections import Counter
from dataclasses import dataclass, field

from src.config import settings
from src.generation import generate as gen_mod
from src.retrieval import (
    bm25_retriever, deduplicator, evidence_builder, guardrails, hybrid_fusion,
    citation_mapper, facets as facet_mod, metadata_filter, metadata_parser, prompt_builder, query_log, query_validator,
    reranker as rerank_mod, response_parser, retrieval_planner, safety, vector_retriever,
)
from src.schemas import Answer, Evidence, GuardrailResult, HardFilter, QueryAnalysis, RetrievalResult


_OUT_OF_SCOPE_PATTERNS = [
    r"\bcapital of\b",
    r"\bweather\b",
    r"\brecipe\b",
    r"\bsports?\b",
    r"\bmovie\b",
    r"\bcelebrity\b",
    r"\bbitcoin\b",
    r"\bcrypto\b",
    r"\bprice prediction\b",
]

_SEC_SCOPE_TERMS = [
    r"\b10-?k\b", r"\b10-?q\b", r"\bsec\b", r"\bedgar\b", r"\bfilings?\b",
    r"\brisk", r"\brevenue", r"\bincome\b", r"\bmargin", r"\bgrowth",
    r"\boutlook\b", r"\bregulatory\b", r"\blegal\b", r"\bmd&?a\b",
    r"\bfinancial", r"\bbusiness\b", r"\bsegment",
]

_SECTION_EXPANSIONS = {
    "Risk Factors": "risk factors Item 1A headwinds uncertainty exposure regulatory risk",
    "Management's Discussion and Analysis": (
        "management discussion analysis MD&A results of operations liquidity capital resources "
        "outlook growth outlook revenue growth subscription revenue subscriber volume advertising"
    ),
    "Financial Statements and Supplementary Data": (
        "financial statements revenue income cash flow balance sheet margin net income "
        "consolidated statements net sales revenue table advertising revenue"
    ),
    "Legal Proceedings": (
        "legal proceedings litigation lawsuit regulatory investigation government inquiry settlement claims"
    ),
    "Business": "business model business products services customers members membership segments strategy markets",
}

_SECTION_SIGNAL_FIELDS = {
    "Risk Factors": ("has_risk_heading",),
    "Management's Discussion and Analysis": ("has_mda_heading", "has_revenue_table"),
    "Financial Statements and Supplementary Data": ("has_financial_table", "has_revenue_table"),
    "Legal Proceedings": ("has_legal_heading",),
    "Business": ("has_business_heading",),
}

_FACET_QUOTAS = {
    "risk": 2,
    "legal": 1,
    "regulatory": 1,
    "financial": 2,
    "revenue_trend": 2,
    "liquidity": 1,
    "segments": 2,
    "business": 1,
    "market_risk": 1,
}

_DEFAULT_EVIDENCE_TOP_K = settings.rerank_top_k
_SINGLE_COMPANY_TOP_K = 6
_TREND_TOP_K = 10
_COMPARISON_TOP_K = 12


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


def _out_of_scope_reason(qa: QueryAnalysis) -> str:
    q = qa.query.lower()
    if any(re.search(p, q) for p in _OUT_OF_SCOPE_PATTERNS):
        return (
            "Question is outside the SEC filings corpus. Ask about covered companies, filings, "
            "risks, financials, MD&A, legal proceedings, or business performance."
        )
    if qa.companies or qa.section_intent:
        return ""
    if any(re.search(p, q) for p in _SEC_SCOPE_TERMS):
        return ""
    return (
        "Question does not name a covered company, filing topic, or SEC filing concept. "
        "Ask about SEC filings, company risks, financials, MD&A, legal proceedings, or business performance."
    )


def _entity_filter(base: HardFilter, ticker: str) -> HardFilter:
    return HardFilter(
        tickers=[ticker],
        years=base.years,
        quarters=base.quarters,
        forms=base.forms,
        fiscal_periods=base.fiscal_periods,
    )


def _interleave_ranked(groups: list[list[RetrievalResult]]) -> list[RetrievalResult]:
    """Round-robin ranked lists so multi-company retrieval stays balanced."""
    out: list[RetrievalResult] = []
    seen: set[str] = set()
    max_len = max((len(g) for g in groups), default=0)
    for i in range(max_len):
        for group in groups:
            if i >= len(group):
                continue
            result = group[i]
            cid = result.chunk.id
            if cid in seen:
                continue
            seen.add(cid)
            out.append(result)
    return out


def _expanded_query(q: str, section_boosts: list[str]) -> str:
    additions = [
        _SECTION_EXPANSIONS[section]
        for section in section_boosts
        if section in _SECTION_EXPANSIONS
    ]
    if not additions:
        return q
    return f"{q} {' '.join(additions)}"


def _section_match(section: str, target: str) -> bool:
    left = section.lower()
    right = target.lower()
    return left == right or left in right or right in left


def _chunk_matches_section(result: RetrievalResult | Evidence, target: str,
                           facets: list[str] | tuple[str, ...] = ()) -> bool:
    chunk = result.chunk
    if facet_mod.chunk_matches_section(chunk, target, facets=facets):
        return True
    # Backward-compatible fallback for pre-facet tests/fakes.
    if _section_match(chunk.section or "", target):
        return True
    if any(bool(getattr(chunk, field, False)) for field in _SECTION_SIGNAL_FIELDS.get(target, ())):
        return True
    signals = (getattr(chunk, "section_signals", "") or "").lower()
    target_terms = target.lower().replace("management's discussion and analysis", "mda")
    return any(term in signals for term in target_terms.replace("&", " ").split())


def _section_bonus(chunk, section_boosts: list[str],
                   facets: list[str] | tuple[str, ...] = ()) -> float:
    if not section_boosts and not facets:
        return 0.0
    bonus = 0.0
    for facet in facets:
        if facet_mod.chunk_matches_facet(chunk, facet):
            bonus = max(bonus, 0.07)
    for target in section_boosts:
        if facet_mod.chunk_matches_section(chunk, target, facets=facets):
            bonus = max(bonus, 0.08)
        elif any(bool(getattr(chunk, field, False)) for field in _SECTION_SIGNAL_FIELDS.get(target, ())):
            bonus = max(bonus, 0.06)
    quality = float(getattr(chunk, "metadata_quality", 0.0) or 0.0)
    return bonus + min(0.02, max(0.0, quality - 0.75) * 0.05)


def _apply_section_boosts(
    results: list[RetrievalResult],
    section_boosts: list[str],
    facets: list[str] | tuple[str, ...] = (),
) -> list[RetrievalResult]:
    if not section_boosts and not facets:
        return results
    boosted: list[RetrievalResult] = []
    for r in results:
        boosted.append(
            RetrievalResult(
                chunk=r.chunk,
                score=r.score + _section_bonus(r.chunk, section_boosts, facets),
            )
        )
    boosted.sort(key=lambda r: r.score, reverse=True)
    return boosted


def _coverage_first_order(
    results: list[RetrievalResult],
    section_boosts: list[str],
    facets: list[str] | tuple[str, ...] = (),
) -> list[RetrievalResult]:
    """Move best facet/section matches to the front before diversity truncation."""
    if not section_boosts and not facets:
        return results
    selected: list[RetrievalResult] = []
    used: set[str] = set()
    for facet in facets:
        quota = _FACET_QUOTAS.get(facet, 1)
        taken = 0
        for r in results:
            if r.chunk.id in used:
                continue
            if facet_mod.chunk_matches_facet(r.chunk, facet):
                selected.append(r)
                used.add(r.chunk.id)
                taken += 1
                if taken >= quota:
                    break
    for target in section_boosts:
        for r in results:
            if r.chunk.id in used:
                continue
            if _chunk_matches_section(r, target, facets):
                selected.append(r)
                used.add(r.chunk.id)
                break
    selected.extend(r for r in results if r.chunk.id not in used)
    return selected


def _evidence_limit(qa: QueryAnalysis) -> int:
    if "Comparison" in qa.intents or len(qa.companies) >= 2:
        return _COMPARISON_TOP_K
    if "Trend" in qa.intents or "Temporal" in qa.intents:
        return _TREND_TOP_K
    if len(qa.companies) == 1:
        return _SINGLE_COMPANY_TOP_K
    return _DEFAULT_EVIDENCE_TOP_K


def _diversify_results(results: list[RetrievalResult], *, limit: int) -> list[RetrievalResult]:
    """Select a ranked but section/company-diverse evidence pool."""
    selected: list[RetrievalResult] = []
    used: set[str] = set()
    section_counts: Counter[str] = Counter()
    company_counts: Counter[str] = Counter()

    def add(r: RetrievalResult, *, section_cap: int | None = None,
            company_cap: int | None = None, unique_pair: bool = False) -> None:
        if len(selected) >= limit or r.chunk.id in used:
            return
        section = r.chunk.section or ""
        company = r.chunk.ticker or r.chunk.company or ""
        if unique_pair and any(
            (x.chunk.ticker or x.chunk.company or "", x.chunk.section or "") == (company, section)
            for x in selected
        ):
            return
        if section_cap is not None and section_counts[section] >= section_cap:
            return
        if company_cap is not None and company_counts[company] >= company_cap:
            return
        selected.append(r)
        used.add(r.chunk.id)
        section_counts[section] += 1
        company_counts[company] += 1

    for r in results:
        add(r, unique_pair=True)
    for r in results:
        add(r, section_cap=max(2, limit // 3), company_cap=max(2, limit // 2))
    for r in results:
        add(r)
    return selected


def _retrieval_confidence(qa: QueryAnalysis, hard: HardFilter, evidence: list[Evidence], *,
                          top_similarity: float, evidence_limit: int) -> dict:
    if not evidence:
        return {"score": 0.0, "band": "Low", "components": {}}

    md_checks = [hard.matches(e.chunk.metadata()) for e in evidence] if not hard.is_empty else []
    metadata_match = sum(md_checks) / len(md_checks) if md_checks else 0.75

    scores = [e.score for e in evidence]
    top_score = max((abs(s) for s in scores), default=0.0)
    reranker_signal = 0.0 if top_score == 0 else max(0.0, min(1.0, sum(scores) / len(scores) / top_score))

    facet_cov = None
    if qa.facets:
        cov = facet_mod.facet_coverage([e.chunk for e in evidence], qa.facets)
        required = len(cov["required"])
        facet_cov = len(cov["covered"]) / required if required else 1.0

    if qa.companies:
        covered = {e.chunk.ticker for e in evidence if e.chunk.ticker}
        entity_cov = len([c for c in qa.companies if c in covered]) / max(len(qa.companies), 1)
        coverage = (entity_cov + facet_cov) / 2 if facet_cov is not None else entity_cov
    elif qa.years:
        years = {e.chunk.year for e in evidence if e.chunk.year}
        year_cov = len([y for y in qa.years if y in years]) / max(len(qa.years), 1)
        coverage = (year_cov + facet_cov) / 2 if facet_cov is not None else year_cov
    elif facet_cov is not None:
        coverage = facet_cov
    elif qa.section_intent:
        sections = {e.chunk.section for e in evidence}
        coverage = len([
            s for s in qa.section_intent
            if any(_section_match(actual, s) for actual in sections)
            or any(_chunk_matches_section(e, s, qa.facets) for e in evidence)
        ]) / max(len(qa.section_intent), 1)
    else:
        coverage = min(1.0, len(evidence) / max(evidence_limit, 1))

    similarity = max(0.0, min(1.0, top_similarity))
    score = (
        0.25 * metadata_match
        + 0.25 * reranker_signal
        + 0.25 * coverage
        + 0.25 * similarity
    )
    band = "High" if score >= 0.75 else "Medium" if score >= 0.55 else "Low"
    return {
        "score": round(score, 3),
        "band": band,
        "components": {
            "metadata_match": round(metadata_match, 3),
            "reranker_score": round(reranker_signal, 3),
            "coverage": round(coverage, 3),
            "similarity": round(similarity, 3),
        },
    }


def _hybrid_search(q: str, qa: QueryAnalysis, hard: HardFilter, plan, *, store, index, embedder,
                   trace: dict) -> tuple[list[RetrievalResult], list[RetrievalResult]]:
    if plan.mode == "per_entity" and qa.companies:
        trace["balanced_entities"] = qa.companies
        trace["per_entity_k"] = plan.per_entity_k
        vector_groups: list[list[RetrievalResult]] = []
        bm25_groups: list[list[RetrievalResult]] = []
        for ticker in qa.companies:
            entity_hard = _entity_filter(hard, ticker)
            if embedder and store:
                vector_groups.append(_try(
                    lambda entity_hard=entity_hard: vector_retriever.search(
                        q, entity_hard, embedder=embedder, store=store, k=plan.per_entity_k
                    ),
                    trace, f"vector_error_{ticker}", default=[],
                ))
            if index:
                bm25_groups.append(_try(
                    lambda entity_hard=entity_hard: bm25_retriever.search(
                        q, entity_hard, index=index, k=plan.per_entity_k
                    ),
                    trace, f"bm25_error_{ticker}", default=[],
                ))
        return _interleave_ranked(vector_groups), _interleave_ranked(bm25_groups)

    vec = _try(lambda: vector_retriever.search(q, hard, embedder=embedder, store=store,
                                               k=settings.vector_top_k),
               trace, "vector_error", default=[]) if embedder and store else []
    bm = _try(lambda: bm25_retriever.search(q, hard, index=index, k=settings.bm25_top_k),
              trace, "bm25_error", default=[]) if index else []
    return vec, bm


def _default_store():
    from src.pipeline.store import ChromaVectorStore
    return ChromaVectorStore()


def _default_index():
    from src.pipeline.store import Bm25Index, _vectorstore_dir
    return Bm25Index.load(_vectorstore_dir() / "bm25.json")


def _default_embedder():
    from src.pipeline.embed import get_embedder
    return get_embedder()


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
        "facets": qa.facets, "facet_targets": plan.facets,
    }

    safety_decision = safety.evaluate_query(q)
    trace["safety_guardrail"] = {
        "ok": safety_decision.ok,
        "category": safety_decision.category,
        "reason": safety_decision.reason,
    }
    if not safety_decision.ok:
        return PipelineResult(answer=response_parser.refusal_answer(safety_decision.reason),
                              analysis=qa, refused=True, trace=trace)

    reason = _out_of_scope_reason(qa)
    if reason:
        trace["scope_guardrail"] = {"ok": False, "reason": reason}
        return PipelineResult(answer=response_parser.refusal_answer(reason), analysis=qa,
                              refused=True, trace=trace)

    retrieval_q = _expanded_query(q, plan.section_boosts)
    if retrieval_q != q:
        trace["expanded_query"] = retrieval_q

    # resolve components (lazy, guarded)
    store = _try(_default_store, trace, "store_error") if store is None else store
    index = _try(_default_index, trace, "index_error") if index is None else index
    embedder = _try(_default_embedder, trace, "embedder_error") if embedder is None else embedder

    # Stage 6 — hybrid retrieval with fallback (§9)
    vec, bm = _hybrid_search(retrieval_q, qa, hard, plan, store=store, index=index,
                             embedder=embedder, trace=trace)
    trace["vector_ids"] = [r.chunk.id for r in vec]
    trace["bm25_ids"] = [r.chunk.id for r in bm]
    if not vec and not bm:
        return PipelineResult(
            answer=response_parser.refusal_answer("No relevant evidence was retrieved."),
            analysis=qa, refused=True, trace=trace)

    # Stage 7 — RRF fusion
    fused = hybrid_fusion.reciprocal_rank_fusion(
        vec, bm, top_n=plan.pool_size or settings.candidate_pool)
    fused = _apply_section_boosts(fused, plan.section_boosts, plan.facets)
    trace["rrf_ids"] = [r.chunk.id for r in fused]
    if store is not None:                                     # hydrate BM25-only texts for reranking
        _try(lambda: vector_retriever.hydrate_texts(fused, store), trace, "hydrate_error")

    # Stage 8 — rerank (skip-on-fail handled inside rerank_mod.rerank)
    reranked = rerank_mod.rerank(q, fused, reranker=reranker, top_k=len(fused))
    reranked = _apply_section_boosts(reranked, plan.section_boosts, plan.facets)
    trace["reranked_ids"] = [r.chunk.id for r in reranked]

    # Stage 9 — dedup, Stages 10-11 — evidence
    evidence_limit = _evidence_limit(qa)
    prioritized = _coverage_first_order(
        deduplicator.deduplicate(reranked), plan.section_boosts, plan.facets
    )
    trace["section_prioritized_ids"] = [r.chunk.id for r in prioritized]
    diversified = _diversify_results(prioritized, limit=evidence_limit)
    trace["evidence_limit"] = evidence_limit
    trace["diversified_ids"] = [r.chunk.id for r in diversified]
    evidence = evidence_builder.build_evidence(diversified, limit=evidence_limit)
    trace["evidence_ids"] = [e.chunk.id for e in evidence]
    trace["facet_coverage"] = facet_mod.facet_coverage([e.chunk for e in evidence], plan.facets)

    # Stage 12 — guardrails (top_similarity from the vector cosine; neutral if vector was down)
    top_sim = max((r.score for r in vec), default=settings.min_similarity)
    gr = guardrails.evaluate(qa, evidence, top_similarity=top_sim)
    retrieval_conf = _retrieval_confidence(
        qa, hard, evidence, top_similarity=top_sim, evidence_limit=evidence_limit
    )
    trace["retrieval_confidence"] = retrieval_conf
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
    trace["evidence_dropped_for_budget"] = [
        e.evidence_id for e in evidence if e.evidence_id not in trace["evidence_used"]
    ]

    # Stage 14 — THE single LLM call
    body = gen_mod.generate(prompt, generator=generator)
    body.confidence = retrieval_conf["band"]                 # deterministic confidence is authoritative
    inline_cited = [
        eid for eid in citation_mapper.inline_ids(body)
        if eid in {e.evidence_id for e in kept}
    ]
    body = citation_mapper.with_complete_source_list(body, kept)

    # Stages 15-16 — parse + citations
    retrieved = [RetrievalResult(chunk=e.chunk, score=e.score) for e in kept]
    answer = response_parser.build_answer(body, kept, retrieved=retrieved, usage={})
    available_eids = {e.evidence_id for e in kept}
    cited = [eid for eid in citation_mapper.referenced_ids(body) if eid in available_eids]
    cited_set = set(cited)
    trace["inline_answer_citations"] = inline_cited
    trace["uncited_inline_evidence"] = [e.evidence_id for e in kept if e.evidence_id not in set(inline_cited)]
    trace["answer_citations"] = cited
    trace["uncited_evidence"] = [e.evidence_id for e in kept if e.evidence_id not in cited_set]
    trace["answer_citation_coverage"] = round(len(cited_set) / max(len(kept), 1), 3)
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

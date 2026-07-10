"""P21 tests: ranking + citation metrics, relevance judgment, per-case scoring, aggregation, golden set."""

from src.eval import metrics, relevance
from src.eval.run_eval import aggregate, evaluate_case, is_relevant, load_eval_set
from src.retrieval.retrieval_pipeline import PipelineResult
from src.schemas import Answer, Chunk, Citation, DocMetadata, Evidence


# --- metrics ---

def test_precision_recall_hit():
    rel = [1, 0, 1, 0]
    assert metrics.precision_at_k(rel, 4) == 0.5
    assert metrics.recall_at_k(rel, total_relevant=2, k=4) == 1.0
    assert metrics.hit_at_k(rel, 1) == 1.0
    assert metrics.hit_at_k([0, 0, 1], 2) == 0.0


def test_reciprocal_rank_and_mrr():
    assert metrics.reciprocal_rank([0, 1, 0]) == 0.5
    assert metrics.reciprocal_rank([0, 0, 0]) == 0.0
    assert metrics.mrr([[1], [0, 1]]) == (1.0 + 0.5) / 2


def test_ndcg_perfect_and_imperfect():
    assert metrics.ndcg_at_k([1, 1, 0], 3) == 1.0                 # already ideal
    assert 0.0 < metrics.ndcg_at_k([0, 1, 1], 3) < 1.0           # relevant items ranked lower


def test_citation_metrics():
    assert metrics.citation_groundedness(["E1", "E9"], ["E1", "E2"]) == 0.5   # E9 hallucinated
    assert metrics.citation_groundedness([], ["E1"]) == 0.0
    assert metrics.citation_coverage(["E1"], ["E1", "E2"]) == 0.5             # used 1 of 2


# --- harness ---

def _chunk(ticker="AAPL", year=2024, section="Risk Factors"):
    return Chunk.from_metadata(
        DocMetadata(company=f"{ticker} Inc", ticker=ticker, form="10-K", filing_date=f"{year}-11-01",
                    source_file=f"{ticker}_10K_{year}_full.txt", year=year),
        id=f"{ticker}_{year}_{section[:4]}", doc_id=f"{ticker}_10K_{year}", chunk_index=0,
        section=section, text="body",
    )


def _result(evidence, sources=None, refused=False):
    return PipelineResult(answer=Answer(answer="a", sources=sources or []),
                          evidence=evidence, refused=refused, trace={})


def test_is_relevant_matches_metadata():
    exp = {"companies": ["AAPL"], "sections": ["Risk Factors"], "years": [2024]}
    assert is_relevant(_chunk("AAPL", 2024, "Risk Factors"), exp)
    assert not is_relevant(_chunk("TSLA", 2024, "Risk Factors"), exp)     # wrong company
    assert not is_relevant(_chunk("AAPL", 2023, "Risk Factors"), exp)     # wrong year
    assert not is_relevant(_chunk("AAPL", 2024, "Business"), exp)         # wrong section


def test_business_segments_accepts_mda_equivalent_with_signal():
    c = _chunk("AMZN", 2026, "Management's Discussion and Analysis").model_copy(
        update={"has_business_heading": True, "section_signals": "business_model_content"}
    )
    exp = {
        "question": "Summarize Amazon's business segments",
        "companies": ["AMZN"],
        "sections": ["Business"],
    }
    assert is_relevant(c, exp)


def test_evaluate_case_scores_relevant_evidence():
    ev = [Evidence(evidence_id="E1", chunk=_chunk("AAPL", 2024, "Risk Factors"),
                   tag="[AAPL 10-K FY2024 · Risk Factors]"),
          Evidence(evidence_id="E2", chunk=_chunk("TSLA", 2024, "Business"), tag="[t2]")]
    res = _result(ev, sources=[Citation(tag="[AAPL 10-K FY2024 · Risk Factors]")])
    row = evaluate_case(res, {"companies": ["AAPL"], "sections": ["Risk Factors"]}, k=2)
    assert row["precision@k"] == 0.5 and row["hit@k"] == 1.0 and row["mrr"] == 1.0
    assert row["company_recall"] == 1.0
    assert row["citation_groundedness"] == 1.0                            # E1 cited & present


def test_evaluate_expected_refusal():
    row = evaluate_case(_result([], refused=True), {"expect_refusal": True})
    assert row["refusal_correct"] == 1.0
    row2 = evaluate_case(_result([], refused=False), {"expect_refusal": True})
    assert row2["refusal_correct"] == 0.0


def test_aggregate_means():
    rows = [{"precision@k": 1.0, "mrr": 1.0}, {"precision@k": 0.0, "mrr": 0.5}]
    agg = aggregate(rows)
    assert agg["precision@k"] == 0.5 and agg["mrr"] == 0.75 and agg["n_cases"] == 2


def test_golden_set_loads():
    cases = load_eval_set()
    assert len(cases) >= 20                                               # ~25 representative questions
    assert all("question" in c and "id" in c for c in cases)
    assert any(c.get("expect_refusal") for c in cases)                    # includes out-of-corpus cases
    assert len({c["id"] for c in cases}) == len(cases)                    # ids unique


def test_relevance_by_chunk_id_and_pooled_recall():
    c = _chunk("AAPL", 2024, "Risk Factors")
    assert relevance.is_relevant(c, {"expected_chunk_ids": [c.id]})       # exact-id ground truth
    assert not relevance.is_relevant(c, {"expected_chunk_ids": ["other"]})
    assert relevance.company_recall([c], {"companies": ["AAPL", "TSLA"]}) == 0.5
    assert metrics != relevance                                           # both modules import cleanly

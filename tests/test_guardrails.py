"""Stage 12 tests: the guardrail decision table (reject/warn/accept, coverage, diversity, bands)."""

from src.retrieval.guardrails import evaluate
from src.schemas import Chunk, DocMetadata, Evidence, QueryAnalysis


def _ev(eid, ticker="AAPL", year=2024, section="Risk Factors"):
    c = Chunk.from_metadata(
        DocMetadata(company=f"{ticker} Inc", ticker=ticker, form="10-K", filing_date=f"{year}-11-01",
                    source_file=f"{ticker}_10K_{year}_full.txt", year=year),
        id=f"{ticker}_{year}_{eid}", doc_id=f"{ticker}_10K_{year}", chunk_index=0,
        section=section, text="body",
    )
    return Evidence(evidence_id=eid, chunk=c, score=0.9, tag="[t]")


def test_no_evidence_rejected():
    r = evaluate(QueryAnalysis(query="q"), [], top_similarity=0.9)
    assert not r.ok and r.action == "reject"


def test_below_similarity_threshold_rejected():
    r = evaluate(QueryAnalysis(query="q"), [_ev("E1")], top_similarity=0.20)
    assert not r.ok and "threshold" in r.reason and r.confidence == "Low"


def test_missing_company_rejected_and_named():
    qa = QueryAnalysis(query="Apple vs Tesla", companies=["AAPL", "TSLA"], intents=["Comparison", "MultiCompany"])
    r = evaluate(qa, [_ev("E1", "AAPL")], top_similarity=0.8)      # TSLA missing
    assert not r.ok and "TSLA" in r.reason


def test_comparison_needs_two_companies():
    qa = QueryAnalysis(query="compare the leading automakers", intents=["Comparison"])  # no tickers named
    r = evaluate(qa, [_ev("E1", "TSLA")], top_similarity=0.8)      # only one company in evidence
    assert not r.ok and "two companies" in r.reason


def test_single_company_temporal_comparison_not_rejected():
    qa = QueryAnalysis(query="compare Apple 2023 vs 2024", companies=["AAPL"],
                       intents=["Comparison", "SingleCompany"], years=[2023, 2024])
    ev = [_ev("E1", "AAPL", 2023), _ev("E2", "AAPL", 2024)]
    r = evaluate(qa, ev, top_similarity=0.8)
    assert r.ok                                                    # single-company comparison is valid


def test_accept_and_confidence_bands():
    ev = [_ev("E1")]
    assert evaluate(QueryAnalysis(query="q"), ev, top_similarity=0.80).confidence == "High"
    assert evaluate(QueryAnalysis(query="q"), ev, top_similarity=0.60).confidence == "Medium"
    r_warn = evaluate(QueryAnalysis(query="q"), ev, top_similarity=0.40)
    assert r_warn.ok and r_warn.action == "warn" and r_warn.confidence == "Low"
    assert evaluate(QueryAnalysis(query="q"), ev, top_similarity=0.80).action == "accept"


def test_missing_year_warns_but_answers():
    qa = QueryAnalysis(query="Apple 2020 revenue", companies=["AAPL"], years=[2020])
    r = evaluate(qa, [_ev("E1", "AAPL", 2024)], top_similarity=0.8)  # only 2024 evidence
    assert r.ok and r.action == "warn" and "2020" in r.reason

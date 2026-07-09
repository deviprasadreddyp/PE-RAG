"""Stage 13 tests: prompt shape, cite-or-refuse system rules, versioning, token-budget trimming."""

from src.retrieval.evidence_builder import build_evidence
from src.retrieval.prompt_builder import PROMPT_VERSION, build_prompt, fit_to_budget
from src.schemas import Chunk, DocMetadata, QueryAnalysis, RetrievalResult


def _rr(cid, text="net sales rose to $391,035 million", score=0.9):
    c = Chunk.from_metadata(
        DocMetadata(company="Apple Inc", ticker="AAPL", form="10-K", filing_date="2024-11-01",
                    source_file="AAPL_10K_2024_full.txt", year=2024),
        id=cid, doc_id="AAPL_10K_2024", chunk_index=0, section="Risk Factors", text=text,
    )
    return RetrievalResult(chunk=c, score=score)


def test_prompt_shape_and_version():
    ev = build_evidence([_rr("AAPL_10K_2024__RiskFactors_c00")])
    p = build_prompt(QueryAnalysis(query="What were Apple's net sales?"), ev)
    assert p.prompt_version == PROMPT_VERSION
    assert "<context>" in p.user and "E1:" in p.user
    assert "Question: What were Apple's net sales?" in p.user
    assert "Output format:" in p.user


def test_system_has_cite_or_refuse_rules():
    assert "ONLY from the SEC" in SYSTEM_TEXT()
    assert "Information unavailable in the provided filings." in SYSTEM_TEXT()
    assert "[E1]" in SYSTEM_TEXT()


def SYSTEM_TEXT():
    from src.retrieval.prompt_builder import SYSTEM
    return SYSTEM


def test_numbers_preserved_verbatim_in_context():
    ev = build_evidence([_rr("c0", text="Total net sales were $391,035 million in fiscal 2022.")])
    p = build_prompt(QueryAnalysis(query="net sales?"), ev)
    assert "$391,035 million" in p.user


def test_fit_to_budget_trims_lowest_ranked():
    big = "word " * 4000                                     # ~5000 chars -> ~1250 tokens each
    ev = build_evidence([_rr(f"c{i}", text=big) for i in range(10)], limit=10)
    kept = fit_to_budget(ev, "q", max_input_tokens=3000)
    assert 0 < len(kept) < 10                                # trimmed to fit
    assert [e.evidence_id for e in kept] == [f"E{i+1}" for i in range(len(kept))]  # best-first kept


def test_fit_to_budget_keeps_at_least_one():
    huge = "x" * 100000
    ev = build_evidence([_rr("c0", text=huge)], limit=1)
    assert len(fit_to_budget(ev, "q", max_input_tokens=10)) == 1

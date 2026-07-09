"""Stages 10-11 tests: [E#] grounding ids, citation tags, cap, context rendering."""

from src.retrieval.evidence_builder import build_evidence, evidence_tag, render_context
from src.schemas import Chunk, DocMetadata, RetrievalResult


def _rr(cid, ticker="AAPL", year=2024, section="Risk Factors", text="supply-chain risk", score=0.9):
    c = Chunk.from_metadata(
        DocMetadata(company=f"{ticker} Inc", ticker=ticker, form="10-K", filing_date=f"{year}-11-01",
                    source_file=f"{ticker}_10K_{year}_full.txt", year=year),
        id=cid, doc_id=f"{ticker}_10K_{year}", chunk_index=0, section=section, text=text,
    )
    return RetrievalResult(chunk=c, score=score)


def test_evidence_ids_and_tag():
    ev = build_evidence([_rr("AAPL_10K_2024__RiskFactors_c00"), _rr("TSLA_10K_2024__RiskFactors_c00", "TSLA")])
    assert [e.evidence_id for e in ev] == ["E1", "E2"]
    assert ev[0].tag == "[AAPL 10-K FY2024 · Risk Factors]"
    assert ev[1].chunk.ticker == "TSLA"


def test_cap_at_limit():
    rs = [_rr(f"c{i}") for i in range(20)]
    assert len(build_evidence(rs, limit=8)) == 8


def test_render_context_has_ids_tags_and_text():
    ev = build_evidence([_rr("AAPL_10K_2024__RiskFactors_c00", text="the body")])
    ctx = render_context(ev)
    assert "E1: [AAPL 10-K FY2024 · Risk Factors]" in ctx
    assert "chunk AAPL_10K_2024__RiskFactors_c00" in ctx
    assert "the body" in ctx


def test_render_context_separates_blocks():
    ev = build_evidence([_rr("a"), _rr("b")])
    assert "\n---\n" in render_context(ev)


def test_tag_without_section():
    c = _rr("x", section="").chunk
    assert evidence_tag(c) == "[AAPL 10-K FY2024]"

"""Stages 15-16 tests: citation mapping ([E#] resolve + drop unknown), markdown, refusal."""

from src.retrieval.citation_mapper import inline_ids, map_citations, referenced_ids, with_complete_source_list
from src.retrieval.evidence_builder import build_evidence
from src.retrieval.response_parser import REFUSAL, build_answer, refusal_answer, render_markdown
from src.schemas import AnswerBody, Chunk, DocMetadata, RetrievalResult


def _ev(cids):
    rrs = []
    for cid, ticker, section in cids:
        c = Chunk.from_metadata(
            DocMetadata(company=f"{ticker} Inc", ticker=ticker, form="10-K",
                        filing_date="2024-11-01", source_file=f"{ticker}_10K_2024_full.txt",
                        year=2024, source_url=f"https://sec.gov/{ticker}"),
            id=cid, doc_id=f"{ticker}_10K_2024", chunk_index=0, section=section, text="body",
        )
        rrs.append(RetrievalResult(chunk=c, score=0.9))
    return build_evidence(rrs)


def test_referenced_ids_from_list_and_text():
    body = AnswerBody(citations=["E1"], supporting_evidence="also see [E3] and [E1]")
    assert referenced_ids(body) == ["E1", "E3"]              # E1 from list, E3 from text, deduped
    assert inline_ids(body) == ["E3", "E1"]


def test_complete_source_list_adds_prompt_evidence_after_inline_cites():
    ev = _ev([("AAPL_c0", "AAPL", "Risk Factors"), ("TSLA_c0", "TSLA", "Business")])
    body = AnswerBody(citations=[], executive_summary="Apple risk [E1].")
    completed = with_complete_source_list(body, ev)
    assert completed.citations == ["E1", "E2"]


def test_map_citations_resolves_and_drops_unknown():
    ev = _ev([("AAPL_c0", "AAPL", "Risk Factors"), ("TSLA_c0", "TSLA", "Business")])
    body = AnswerBody(citations=["E1", "E9"], supporting_evidence="[E2]")  # E9 unknown
    cites = map_citations(body, ev)
    assert [c.ticker for c in cites] == ["AAPL", "TSLA"]     # E1->AAPL, E2->TSLA; E9 dropped
    assert cites[0].section == "Risk Factors" and cites[0].source_url == "https://sec.gov/AAPL"
    assert cites[0].fiscal_period == "FY2024"


def test_render_markdown_sections():
    md = render_markdown(AnswerBody(executive_summary="Sales up.", comparison="A>B",
                                    supporting_evidence="[E1]", confidence="High"))
    assert "## Executive Summary" in md and "## Comparison" in md
    assert "## Supporting Evidence" in md and "**Confidence:** High" in md
    assert "## Citations" in md and "[E1]" in md


def test_build_answer_attaches_sources():
    ev = _ev([("AAPL_c0", "AAPL", "Risk Factors")])
    body = AnswerBody(executive_summary="Apple faces supply risk [E1].", citations=["E1"], confidence="High")
    ans = build_answer(body, ev, usage={"input_tokens": 100})
    assert ans.sources and ans.sources[0].ticker == "AAPL"
    assert "Executive Summary" in ans.answer and ans.usage["input_tokens"] == 100


def test_refusal_answer():
    a = refusal_answer("A comparison needs two companies.")
    assert a.answer.startswith(REFUSAL) and "two companies" in a.answer and a.sources == []

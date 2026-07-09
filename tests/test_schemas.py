"""Schema tests: construction, JSON round-trips, Chroma-safe metadata, strictness."""

import pytest
from pydantic import ValidationError

from src.schemas import (
    Answer, AnswerBody, Chunk, Citation, DocMetadata, Document, EmbeddingRecord,
    Evidence, GuardrailResult, HardFilter, PromptBundle, QueryAnalysis, RetrievalPlan,
    RetrievalResult, SectionSpan,
)


def _meta(**kw) -> DocMetadata:
    base = dict(
        company="Apple Inc", ticker="AAPL", form="10-K",
        filing_date="2022-10-28", source_file="AAPL_10K_2022Q3_2022-10-28_full.txt",
        fiscal_period="2022Q3", year=2022, quarter="Q3", cik="0000320193",
        source_url="https://sec.gov/x",
    )
    base.update(kw)
    return DocMetadata(**base)


def _chunk(**kw) -> Chunk:
    return Chunk.from_metadata(
        _meta(), id="AAPL_10K_2024_0", doc_id="AAPL_10K_2024", chunk_index=0,
        section="Risk Factors", text="Supply chain risk...", embed_text="Company: Apple ...", **kw
    )


def test_docmetadata_defaults_and_roundtrip():
    m = _meta()
    assert m.report_period == "" and m.quarter == "Q3"
    assert DocMetadata.model_validate_json(m.model_dump_json()) == m


def test_sectionspan_offsets_valid():
    s = SectionSpan(section_name="Risk Factors", item="Item 1A", start=100, end=500)
    assert SectionSpan.model_validate_json(s.model_dump_json()) == s
    with pytest.raises(ValidationError):
        SectionSpan(section_name="x", start=500, end=100)


def test_chunk_inherits_all_metadata_and_roundtrips():
    c = _chunk()
    assert c.ticker == "AAPL" and c.form == "10-K" and c.fiscal_period == "2022Q3"
    assert Chunk.model_validate_json(c.model_dump_json()) == c


def test_chunk_metadata_is_chroma_safe():
    md = _chunk().metadata()
    assert "text" not in md and "embed_text" not in md
    for k, v in md.items():
        assert v is not None, f"{k} is None"
        assert isinstance(v, (str, int, float, bool)), f"{k}={v!r} not Chroma-safe"
    assert md["ticker"] == "AAPL" and md["section"] == "Risk Factors"


def test_retrieval_result_and_answer_roundtrip():
    rr = RetrievalResult(chunk=_chunk(), score=0.83)
    ans = Answer(
        answer="Apple faces supply-chain risk [AAPL 10-K FY2022 · Item 1A Risk Factors].",
        sources=[Citation(tag="[AAPL 10-K FY2022 · Item 1A Risk Factors]", ticker="AAPL",
                          form="10-K", fiscal_period="2022Q3", section="Risk Factors")],
        retrieved=[rr],
        usage={"input_tokens": 1200, "output_tokens": 300},
    )
    assert Answer.model_validate_json(ans.model_dump_json()) == ans
    assert ans.retrieved[0].chunk.ticker == "AAPL"


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        DocMetadata(company="x", ticker="X", form="10-K", filing_date="2024-01-01",
                    source_file="x.txt", bogus="nope")


def test_document_roundtrip_and_default_status():
    d = Document(doc_id="AAPL_10K_2024", filename="AAPL_10K_2024_full.txt",
                 sha256="a" * 64, size=1024)
    assert d.status == "ok"
    assert Document.model_validate_json(d.model_dump_json()) == d


def test_embedding_record_roundtrip():
    e = EmbeddingRecord(chunk_id="AAPL_10K_2024__RiskFactors_c00",
                        embedding=[0.1, -0.2, 0.3], metadata={"ticker": "AAPL", "year": 2024})
    assert EmbeddingRecord.model_validate_json(e.model_dump_json()) == e


# --- Phase 2 contracts ---

def test_query_analysis_defaults_and_roundtrip():
    q = QueryAnalysis(query="Compare Apple and Tesla risk factors in 2024",
                      intents=["Comparison", "Risk"], companies=["AAPL", "TSLA"],
                      years=[2024], section_intent=["Risk Factors"])
    assert q.quarters == [] and q.forms == []
    assert QueryAnalysis.model_validate_json(q.model_dump_json()) == q


def test_hard_filter_where_and_matches():
    f = HardFilter(tickers=["AAPL", "TSLA"], years=[2024], forms=["10-K"])
    assert not f.is_empty
    # single-field filter is a bare clause; multi-field is $and
    assert f.where == {"$and": [
        {"ticker": {"$in": ["AAPL", "TSLA"]}},
        {"year": {"$in": [2024]}},
        {"form": {"$in": ["10-K"]}},
    ]}
    assert f.matches({"ticker": "AAPL", "year": 2024, "form": "10-K"})
    assert not f.matches({"ticker": "MSFT", "year": 2024, "form": "10-K"})   # wrong ticker
    assert not f.matches({"ticker": "AAPL", "year": 2023, "form": "10-K"})   # wrong year


def test_hard_filter_empty_is_no_op():
    f = HardFilter()
    assert f.is_empty and f.where == {}
    assert f.matches({"ticker": "ANY", "year": 1999, "form": "10-Q"})        # matches everything


def test_hard_filter_single_field_is_bare_clause():
    assert HardFilter(tickers=["AAPL"]).where == {"ticker": {"$in": ["AAPL"]}}


def test_retrieval_plan_and_evidence_and_guardrail_roundtrip():
    plan = RetrievalPlan(mode="per_entity", per_entity_k=4, section_boosts=["Risk Factors"])
    assert RetrievalPlan.model_validate_json(plan.model_dump_json()) == plan
    ev = Evidence(evidence_id="E1", chunk=_chunk(), score=0.91, tag="[AAPL 10-K FY2022 · Risk Factors]")
    assert Evidence.model_validate_json(ev.model_dump_json()) == ev
    g = GuardrailResult(ok=False, action="reject", reason="insufficient evidence", confidence="Low")
    assert GuardrailResult.model_validate_json(g.model_dump_json()) == g


def test_prompt_bundle_and_answer_body_roundtrip():
    pb = PromptBundle(system="You are...", user="Question: ...", prompt_version="v1")
    assert PromptBundle.model_validate_json(pb.model_dump_json()) == pb
    ab = AnswerBody(executive_summary="Apple's revenue grew.", supporting_evidence="Net sales [E1].",
                    citations=["E1"], confidence="High")
    assert ab.comparison == "" and ab.limitations == ""
    assert AnswerBody.model_validate_json(ab.model_dump_json()) == ab

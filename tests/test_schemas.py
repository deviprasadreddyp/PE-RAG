"""Schema tests: construction, JSON round-trips, Chroma-safe metadata, strictness."""

import pytest
from pydantic import ValidationError

from src.schemas import Answer, Chunk, Citation, DocMetadata, RetrievalResult, SectionSpan


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

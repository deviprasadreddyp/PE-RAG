"""Facet taxonomy and section-equivalence tests."""

from src.retrieval import facets
from src.schemas import Chunk, DocMetadata


def _chunk(section: str, text: str = "body", **flags) -> Chunk:
    c = Chunk.from_metadata(
        DocMetadata(
            company="Amazon.com, Inc.", ticker="AMZN", form="10-K",
            filing_date="2026-02-01", source_file="AMZN.txt", year=2026,
        ),
        id="AMZN_x", doc_id="AMZN", chunk_index=0, section=section, text=text,
    )
    return c.model_copy(update=flags)


def test_extracts_business_segment_facets():
    out = facets.extract_facets("Summarize Amazon's business segments", sections=["Business"])
    assert "business" in out
    assert "segments" in out


def test_sections_for_facets_expands_segments_to_business_and_mda():
    sections = facets.sections_for_facets(["segments"])
    assert sections == ["Business", "Management's Discussion and Analysis"]


def test_chunk_matches_equivalent_business_mda_with_signal():
    c = _chunk(
        "Management's Discussion and Analysis",
        has_business_heading=True,
        section_signals="business_model_content",
    )
    assert facets.chunk_matches_section(c, "Business", facets=["segments", "business"])
    assert facets.chunk_matches_facet(c, "segments")


def test_facet_coverage_reports_missing():
    chunks = [_chunk("Business", has_business_heading=True)]
    cov = facets.facet_coverage(chunks, ["business", "financial"])
    assert cov["covered"] == ["business"]
    assert cov["missing"] == ["financial"]

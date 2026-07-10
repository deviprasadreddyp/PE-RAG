"""Deterministic post-chunk section resolution tests."""

from src.pipeline.section_resolution import apply_section_resolution, resolve_section
from src.schemas import Chunk, DocMetadata


def _chunk(section: str, text: str) -> Chunk:
    return Chunk.from_metadata(
        DocMetadata(
            company="Example Inc", ticker="EX", form="10-K", filing_date="2026-01-01",
            source_file="EX_10K_2026.txt", year=2026, fiscal_period="2026",
        ),
        id="EX_10K_2026__Other_c00",
        doc_id="EX_10K_2026",
        chunk_index=0,
        section=section,
        text=text,
    )


def test_weak_exhibits_label_becomes_legal_proceedings():
    r = resolve_section(
        "Note 11 - Legal Proceedings Johnson & Johnson is involved in lawsuits and claims.",
        "Exhibits",
    )
    assert r.section == "Legal Proceedings"
    assert r.has_legal_heading
    assert r.source == "heading"


def test_weak_directors_label_becomes_risk_factors_from_content():
    r = resolve_section(
        "Any significant production delays could adversely affect delivery of products.",
        "Directors, Executive Officers and Corporate Governance",
    )
    assert r.section == "Risk Factors"
    assert r.has_risk_heading


def test_weak_summary_label_becomes_mda_for_revenue_trend_content():
    r = resolve_section(
        "Revenue increased in 2025 due to higher volume and subscriber growth trends.",
        "Form 10-K Summary",
    )
    assert r.section == "Management's Discussion and Analysis"
    assert r.has_mda_heading


def test_canonical_section_is_preserved_without_stronger_signal():
    r = resolve_section("We operate globally.", "Business")
    assert r.section == "Business"
    assert r.source == "initial_section"


def test_apply_section_resolution_adds_chroma_safe_metadata():
    c = apply_section_resolution(_chunk("Other", "Item 7. Management's Discussion and Analysis"))
    md = c.metadata()
    assert c.section == "Management's Discussion and Analysis"
    assert c.section_original == "Other"
    assert c.section_confidence > 0.9
    assert c.metadata_quality > 0.0
    for value in md.values():
        assert value is not None
        assert isinstance(value, (str, int, float, bool))

"""Stage 6 tests: text preserved, embed_text header shape, identical format, idempotency."""

import re

from src.observability import load_artifact, persist_artifact
from src.pipeline.enrich import SEP, enrich_chunk, enrich_text, run_enrich
from src.schemas import Chunk, DocMetadata

HEADER = re.compile(
    r"^Company: .+ \(.+\) \| Filing: .+ \| Year: .+ \| Quarter: .+ \| "
    r"Fiscal focus: .+ \| Period end: .* \| CIK: .* \| Amended: .+ \| Section: .+$"
)


def _chunk(section="Risk Factors", text="Supply chain risk.", year=2022,
           fiscal="2022Q3", fdate="2022-10-28", quarter="Q3", i=0) -> Chunk:
    return Chunk.from_metadata(
        DocMetadata(company="Apple Inc", ticker="AAPL", form="10-K", filing_date=fdate,
                    source_file="AAPL_10K_2024_full.txt", fiscal_period=fiscal, year=year,
                    quarter=quarter),
        id=f"AAPL_10K_2024_{i}", doc_id="AAPL_10K_2024", chunk_index=i, section=section, text=text,
    )


def test_original_text_unchanged():
    c = _chunk()
    e = enrich_chunk(c)
    assert e.text == c.text == "Supply chain risk."


def test_embed_text_shape():
    e = enrich_chunk(_chunk())
    assert e.embed_text.startswith(
        "Company: Apple Inc (AAPL) | Filing: 10-K | Year: 2022 | Quarter: Q3 | "
        "Fiscal focus: Q3 | Period end:"
    )
    assert "Amended: no | Section: Risk Factors" in e.embed_text
    assert SEP in e.embed_text and e.embed_text.endswith("Supply chain risk.")


def test_full_year_quarter_is_fy():
    # a 10-K with no quarter shows "Quarter: FY"
    e = enrich_text(_chunk(fiscal="", year=2025, fdate="2025-10-31", quarter=""))
    assert "Quarter: FY" in e


def test_header_format_identical_across_chunks():
    hdrs = [enrich_text(_chunk(section=s)).split(SEP)[0] for s in ("Business", "MD&A")]
    assert all(HEADER.match(h) for h in hdrs)
    # everything before "Section:" is identical (only the section differs)
    a, b = hdrs
    assert a[: a.index("Section:")] == b[: b.index("Section:")]


def test_idempotent_no_stacked_header():
    once = enrich_chunk(_chunk())
    twice = enrich_chunk(once)
    assert once.embed_text == twice.embed_text
    assert once.embed_text.count("Company:") == 1


def test_year_fallback():
    assert enrich_text(_chunk(year=0, fiscal="2023Q2")).startswith(
        "Company: Apple Inc (AAPL) | Filing: 10-K | Year: 2023"
    )
    assert "Year: 2025" in enrich_text(_chunk(year=0, fiscal="", fdate="2025-10-31"))


def test_run_enrich_updates_chunks_in_place(tmp_path):
    persist_artifact(
        "chunks", "AAPL_10K_2024",
        [_chunk(i=0), _chunk(section="Business", text="We design devices.", i=1)],
        base=tmp_path,
    )
    run_enrich("AAPL_10K_2024", base=tmp_path)
    loaded = load_artifact("chunks", "AAPL_10K_2024", base=tmp_path)
    assert all(d["embed_text"].startswith("Company:") for d in loaded)
    assert loaded[0]["text"] == "Supply chain risk."          # original text preserved
    assert "Section: Business" in loaded[1]["embed_text"]

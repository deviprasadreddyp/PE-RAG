"""Stage 5 tests: within-section splitting, stable ids, full metadata, size bounds."""

from src.observability import load_artifact, persist_artifact
from src.pipeline.chunk import chunk_document, make_splitter, run_chunk
from src.schemas import Chunk, DocMetadata, SectionSpan

META = DocMetadata(
    company="Apple Inc", ticker="AAPL", form="10-K", filing_date="2022-10-28",
    source_file="AAPL_10K_2024_full.txt", fiscal_period="2022Q3", year=2022, quarter="Q3",
)
A = "alpha " * 120                                  # section 1 vocabulary
B = "beta " * 120                                   # section 2 vocabulary
CLEANED = A + B
SECTIONS = [
    SectionSpan(section_name="Business", item="Item 1", start=0, end=len(A)),
    SectionSpan(section_name="Risk Factors", item="Item 1A", start=len(A), end=len(A) + len(B)),
]
SPLIT = make_splitter(chunk_size=120, chunk_overlap=20)


def _chunks() -> list[Chunk]:
    return chunk_document("AAPL_10K_2024", META, CLEANED, SECTIONS, splitter=SPLIT)


def test_no_chunk_spans_two_sections():
    for c in _chunks():
        assert ("alpha" in c.text) ^ ("beta" in c.text)          # never both


def test_section_assignment_matches_source():
    for c in _chunks():
        assert c.section == ("Business" if "alpha" in c.text else "Risk Factors")


def test_ids_sequential_and_stable_across_runs():
    a, b = _chunks(), _chunks()
    assert [c.id for c in a] == [f"AAPL_10K_2024_{i}" for i in range(len(a))]
    assert [(c.id, c.text) for c in a] == [(c.id, c.text) for c in b]   # deterministic


def test_sizes_within_bound():
    assert all(len(c.text) <= 120 for c in _chunks())


def test_full_metadata_and_chroma_safe():
    c = _chunks()[0]
    assert c.ticker == "AAPL" and c.form == "10-K" and c.fiscal_period == "2022Q3"
    md = c.metadata()
    assert md["ticker"] == "AAPL" and "text" not in md and "embed_text" not in md
    assert c.embed_text == ""                                     # filled later in Stage 6


def test_empty_section_produces_no_chunks():
    assert chunk_document("D", META, "   ", [SectionSpan(section_name="Other", item="", start=0, end=3)],
                          splitter=SPLIT) == []


def test_run_chunk_reads_inputs_writes_chunks(tmp_path):
    persist_artifact("cleaned", "AAPL_10K_2024", CLEANED, ext="txt", base=tmp_path)
    persist_artifact("metadata", "AAPL_10K_2024", META, base=tmp_path)
    persist_artifact("sections", "AAPL_10K_2024", SECTIONS, base=tmp_path)
    run_chunk("AAPL_10K_2024", base=tmp_path)
    loaded = load_artifact("chunks", "AAPL_10K_2024", base=tmp_path)
    assert loaded and Chunk(**loaded[0]).ticker == "AAPL"

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


def test_ids_are_section_aware_unique_and_stable():
    a, b = _chunks(), _chunks()
    ids = [c.id for c in a]
    assert len(ids) == len(set(ids))                            # unique
    assert all(c.id.startswith("AAPL_10K_2024__") for c in a)   # doc-id prefixed
    biz = [c for c in a if c.section == "Business"]
    risk = [c for c in a if c.section == "Risk Factors"]
    assert biz[0].id == "AAPL_10K_2024__Business_c00"           # section slug + per-section index
    assert risk[0].id == "AAPL_10K_2024__RiskFactors_c00"
    assert [(c.id, c.text) for c in a] == [(c.id, c.text) for c in b]   # deterministic


def test_sizes_within_bound():
    assert all(len(c.text) <= 120 for c in _chunks())


def test_chunk_size_is_a_max_cap_not_fixed():
    # semantic-hierarchical: a section well under the cap stays ONE short chunk
    # (the cap is a ceiling, not a fixed target — nothing is padded to 120 chars)
    small = "Short section body."
    secs = [SectionSpan(section_name="Business", item="Item 1", start=0, end=len(small))]
    cs = chunk_document("D", META, small, secs, splitter=SPLIT)
    assert len(cs) == 1
    assert len(cs[0].text) < 120                                 # size follows content, not the cap


def test_content_hash_is_sha256_of_text():
    import hashlib

    for c in _chunks():
        assert len(c.content_hash) == 64
        assert c.content_hash == hashlib.sha256(c.text.encode("utf-8")).hexdigest()


def test_full_metadata_and_chroma_safe():
    c = _chunks()[0]
    assert c.ticker == "AAPL" and c.form == "10-K" and c.fiscal_period == "2022Q3"
    md = c.metadata()
    assert md["ticker"] == "AAPL" and "text" not in md and "embed_text" not in md
    assert c.embed_text == ""                                     # filled later in Stage 6


def test_hierarchy_indices_parent_and_child():
    cs = _chunks()
    biz = [c for c in cs if c.section == "Business"]
    risk = [c for c in cs if c.section == "Risk Factors"]
    assert all(c.section_index == 0 for c in biz)                 # parent 0
    assert all(c.section_index == 1 for c in risk)                # parent 1
    assert [c.section_chunk_index for c in biz] == list(range(len(biz)))    # child index resets
    assert [c.section_chunk_index for c in risk] == list(range(len(risk)))
    assert [c.chunk_index for c in cs] == list(range(len(cs)))    # global index contiguous


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

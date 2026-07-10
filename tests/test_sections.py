"""Stage 4 tests: nbsp + pipe headings, cross-ref exclusion, TOC/stray drop, contiguity, fallback."""

from src.observability import load_artifact, persist_artifact
from src.pipeline.sections import _clean_title, detect_sections, run_sections
from src.schemas import SectionSpan

FILL = "The company discusses operations and financial results in detail here. " * 15  # >500 chars
TOC = "Item 1. | Business | 1\nItem 1A. | Risk Factors | 5\nItem 7. | MD&A | 25\nItem 9. | Other | 40\n"
STRAY = "Item 9.\xa0\xa0\xa0\xa0Other MattersNone. "                     # high-numbered TOC-tail entry
GAP = "cover and preamble filler text here. " * 20                       # ~740 chars, no headings
DOC = (
    "COVER Apple Inc 10-K.\n" + TOC + STRAY + GAP
    + "Item 1.\xa0\xa0\xa0\xa0BusinessThe Company designs devices. " + FILL
    + "Item 1A.\xa0\xa0\xa0\xa0Risk FactorsThe Company faces risks. "
    + "As described in Item 1A of Part I, risks vary. " + FILL           # cross-ref, must be ignored
    + "Item 7. | Management's Discussion and Analysis of ConditionRevenue grew. " + FILL  # pipe fmt
)


def _spans():
    return detect_sections(DOC)


def test_detects_nbsp_and_pipe_headings_in_order():
    items = [s.item for s in _spans()]
    assert items == ["", "Item 1", "Item 1A", "Item 7"]     # "" is the leading "Other"


def test_titles_are_clean():
    spans = _spans()
    assert spans[1].section_name == "Business"
    assert spans[2].section_name == "Risk Factors"
    assert "Management" in spans[3].section_name


def test_stray_toc_tail_dropped_body_starts_at_item1():
    spans = _spans()
    assert spans[1].item == "Item 1"                         # not the stray "Item 9"
    assert sum(1 for s in spans if s.item == "Item 1A") == 1  # cross-ref did not add a section


def test_spans_contiguous_and_cover_whole_doc():
    spans = _spans()
    assert spans[0].start == 0 and spans[-1].end == len(DOC)
    assert all(spans[i].end == spans[i + 1].start for i in range(len(spans) - 1))


def test_crossrefs_only_falls_back_to_other():
    doc = "See Item 1A of Part I for risks. " * 40
    spans = detect_sections(doc)
    assert len(spans) == 1 and spans[0].section_name == "Other"


def test_lowercase_title_after_item_is_not_a_heading():
    doc = "Part II, Item 1A of the 2024 Form 10-K under the heading Risk Factors. " * 20
    spans = detect_sections(doc)
    assert len(spans) == 1 and spans[0].section_name == "Other"


def test_no_items_single_other_span():
    spans = detect_sections("Plain filing text with no item headings at all. " * 20)
    assert len(spans) == 1 and spans[0].item == "" and spans[0].end == len(
        "Plain filing text with no item headings at all. " * 20
    )


def test_clean_title_camel_split_and_page_numbers():
    assert _clean_title("FactorsThe Company faces") == "Factors"
    assert _clean_title("Business | 1") == "Business"
    assert _clean_title("12") == ""


def test_10k_canonical_names_and_part_tree():
    spans = detect_sections(DOC, "10-K")
    by_item = {s.item: s for s in spans}
    # canonical SEC names replace the detected titles
    assert by_item["Item 1"].section_name == "Business"
    assert by_item["Item 1A"].section_name == "Risk Factors"
    assert by_item["Item 7"].section_name == "Management's Discussion and Analysis"
    # parent Part filled from the fixed 10-K structure (the section tree)
    assert by_item["Item 1"].part == "Part I" and by_item["Item 1A"].part == "Part I"
    assert by_item["Item 7"].part == "Part II"
    assert by_item[""].part == ""                             # the leading "Other" span


def test_10k_drops_late_backtracking_item_hits():
    doc = (
        "Item 1. Business" + FILL
        + "Item 1A. Risk Factors" + FILL
        + "Item 1B. Unresolved Staff Comments" + FILL
        + "Item 1A. Risk Factors are incorporated by reference elsewhere. " + FILL
        + "Item 2. Properties" + FILL
    )
    items = [s.item for s in detect_sections(doc, "10-K")]
    assert items == ["Item 1", "Item 1A", "Item 1B", "Item 2"]


def test_10q_keeps_detected_title_and_no_part():
    spans = detect_sections(DOC, "10-Q")
    by_item = {s.item: s for s in spans}
    # 10-Q items are Part-ambiguous: keep the detected title, never canonicalize/guess a Part
    assert "Management" in by_item["Item 7"].section_name    # detected title, not forced canonical
    assert all(s.part == "" for s in spans)


def test_10q_obvious_titles_are_canonicalized():
    doc = "ITEM 1A. RISK FACTORSOur operations are risky. " + FILL
    spans = detect_sections(doc, "10-Q")
    assert spans[0].section_name == "Risk Factors"


def test_run_sections_reads_cleaned_writes_json(tmp_path):
    persist_artifact("cleaned", "AAPL_10K_2024", DOC, ext="txt", base=tmp_path)
    persist_artifact("metadata", "AAPL_10K_2024",
                     {"company": "Apple", "ticker": "AAPL", "form": "10-K",
                      "filing_date": "2024-01-01", "source_file": "AAPL_10K_2024_full.txt"},
                     base=tmp_path)
    run_sections("AAPL_10K_2024", base=tmp_path)
    loaded = [SectionSpan(**d) for d in load_artifact("sections", "AAPL_10K_2024", base=tmp_path)]
    assert [s.item for s in loaded] == ["", "Item 1", "Item 1A", "Item 7"]
    assert loaded[2].section_name == "Risk Factors" and loaded[2].part == "Part I"  # canonicalized

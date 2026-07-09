"""Stage 2 tests: XBRL stripped, business content preserved, reads raw / writes cleaned."""

from src.observability import load_artifact, persist_artifact
from src.pipeline.clean import clean, run_clean, split_header_body

RAW = (
    "Company: Apple Inc\nTicker: AAPL\n" + "=" * 60 + "\n"
    + "aapl-20220924false2022FY0000320193us-gaap:CommonStockMember2021-09-262022-09-24\n"
    + "0000320193us-gaap:RetainedEarningsMember2020-09-26\n"                 # leading blob
    + "UNITED STATES SECURITIES AND EXCHANGE COMMISSION FORM 10-K\n"
    + "Item 1A. Risk Factors\n"
    + ("The Company faces supply chain and competitive risks. " * 40) + "\n"
    + "Total net sales were $391,035 million in fiscal 2022.\n"
    + "Segment            Revenue\n"
    + "Americas           169,658\n"
    + "0000320193us-gaap:AccumulatedOtherComprehensiveIncomeMember2021-09-25\n"  # residual tag
)


def test_split_header_body():
    header, body = split_header_body(RAW)
    assert "Company: Apple Inc" in header and "FORM 10-K" in body


def test_clean_strips_xbrl_and_preserves_business():
    c = clean(RAW)
    assert "us-gaap:" not in c                            # leading blob + residual removed
    assert "$391,035 million" in c                        # numbers/units preserved verbatim
    assert "Item 1A. Risk Factors" in c                   # section title preserved
    assert "Americas           169,658" in c              # table alignment (internal spaces) kept
    body = split_header_body(RAW)[1]
    assert len(c) < len(RAW)                              # smaller than raw
    assert len(c) > 0.5 * len(body)                       # but kept the bulk (prose dominates)


def test_no_anchor_fallback_keeps_text():
    c = clean("no separator, no anchor here, just text with a number 12345.")
    assert "just text" in c and "12345" in c


def test_run_clean_reads_raw_writes_cleaned(tmp_path):
    persist_artifact("raw", "AAPL_10K_2024", RAW, ext="txt", base=tmp_path)
    rep = run_clean("AAPL_10K_2024", base=tmp_path)
    out = load_artifact("cleaned", "AAPL_10K_2024", ext="txt", base=tmp_path)
    assert "us-gaap:" not in out and "$391,035 million" in out
    assert rep["cleaned_chars"] < rep["raw_chars"]

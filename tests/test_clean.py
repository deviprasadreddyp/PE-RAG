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
    + "Net income  rose sharply.\n"                        # prose w/ multi-space -> collapses
    + "Segment |  | Revenue |  | Change\n"                 # pipe table -> preserved
    + "Americas |  | 169,658 |  | +8%\n"
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
    assert "Americas |  | 169,658 |  | +8%" in c          # pipe table preserved (table-safe)
    assert "Net income rose sharply." in c                # prose multi-space collapsed
    body = split_header_body(RAW)[1]
    assert len(c) < len(RAW)                              # smaller than raw
    assert len(c) > 0.5 * len(body)                       # but kept the bulk (prose dominates)


def test_no_anchor_fallback_keeps_text():
    c = clean("no separator, no anchor here, just text with a number 12345.")
    assert "just text" in c and "12345" in c


def test_clean_removes_xml_infrastructure_but_keeps_business_text():
    raw = (
        "Company: Example\n" + "=" * 60 + "\n"
        "<?xml version=\"1.0\"?><xbrli:xbrl xmlns:dei=\"x\" xmlns:xbrli=\"y\">"
        "<link:schemaRef xlink:href=\"schema.xsd\"/>"
        "<xbrli:context id=\"c1\"><xbrli:entity>parser only</xbrli:entity></xbrli:context>"
        "<xbrli:unit id=\"u1\"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>"
        "</xbrli:xbrl>\n"
        "UNITED STATES SECURITIES AND EXCHANGE COMMISSION FORM 10-K\n"
        "Item 7. Management's Discussion and Analysis\n"
        "Revenue was $10 million.\n"
        "Segment | 2024 | 2023\n"
        "Cloud | $10 | $8\n"
    )
    c = clean(raw)
    assert "schemaRef" not in c and "xbrli:context" not in c and "xmlns:" not in c
    assert "Revenue was $10 million." in c
    assert "Cloud | $10 | $8" in c


def test_run_clean_reads_raw_writes_cleaned(tmp_path):
    persist_artifact("raw", "AAPL_10K_2024", RAW, ext="txt", base=tmp_path)
    rep = run_clean("AAPL_10K_2024", base=tmp_path)
    out = load_artifact("cleaned", "AAPL_10K_2024", ext="txt", base=tmp_path)
    assert "us-gaap:" not in out and "$391,035 million" in out
    assert rep["cleaned_chars"] < rep["raw_chars"]

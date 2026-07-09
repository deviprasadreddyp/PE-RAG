"""Stage 3 tests: header parsing, header-over-filename precedence, filename backfill, normalization."""

from src.observability import load_artifact, persist_artifact
from src.pipeline.metadata import build_metadata, normalize_form, run_metadata
from src.schemas import DocMetadata

SEP = "=" * 60


def _raw(header_lines: str, body: str = "FORM 10-K\nItem 1. Business\n") -> str:
    return header_lines + SEP + "\n" + body


FULL_HEADER = (
    "Company: Apple Inc\nTicker: AAPL\nFiling Type: 10-K (Annual Report)\n"
    "Filing Date: 2022-10-28\nReport Period: 2022-09-24\nQuarter: 2022Q3\n"
    "CIK: 0000320193\nSource: SEC EDGAR\nURL: https://www.sec.gov/x\n"
)


def test_full_header_extraction():
    m = build_metadata("AAPL_10K_2022Q3_2022-10-28", _raw(FULL_HEADER))
    assert m.company == "Apple Inc" and m.ticker == "AAPL"
    assert m.form == "10-K"                              # normalized from "10-K (Annual Report)"
    assert m.filing_date == "2022-10-28" and m.report_period == "2022-09-24"
    assert m.fiscal_period == "2022Q3" and m.quarter == "Q3" and m.year == 2022
    assert m.cik == "0000320193" and m.source_url == "https://www.sec.gov/x"
    assert m.source_file == "AAPL_10K_2022Q3_2022-10-28_full.txt"


def test_header_wins_over_filename():
    # doc_id says ZZZ / 10K, but the header says AAPL / 10-Q — the header must win.
    header = ("Company: Apple Inc\nTicker: AAPL\nFiling Type: 10-Q (Quarterly Report)\n"
              "Filing Date: 2023-05-05\nQuarter: 2023Q2\nCIK: 1\nURL: u\n")
    m = build_metadata("ZZZ_10K_2023Q2_2023-05-05", _raw(header))
    assert m.ticker == "AAPL" and m.form == "10-Q"


def test_backfill_period_from_filename_when_header_missing():
    header = "Company: Apple\nTicker: AAPL\nFiling Type: 10-Q\nFiling Date: 2023-05-05\n"  # no Quarter
    m = build_metadata("AAPL_10Q_2023Q2_2023-05-05", _raw(header))
    assert m.fiscal_period == "2023Q2" and m.quarter == "Q2" and m.year == 2023


def test_annual_without_period():
    header = "Company: Apple\nTicker: AAPL\nFiling Type: 10-K\nFiling Date: 2025-10-31\n"  # no period
    m = build_metadata("AAPL_10K_2025-10-31", _raw(header))
    assert m.fiscal_period == "" and m.quarter == "" and m.year == 2025


def test_form_normalization():
    assert normalize_form("10-K (Annual Report)") == "10-K"
    assert normalize_form("10K") == "10-K"
    assert normalize_form("10-Q") == "10-Q"
    assert normalize_form("nonsense") == ""


def test_run_metadata_reads_raw_writes_json(tmp_path):
    persist_artifact("raw", "AAPL_10K_2022Q3_2022-10-28", _raw(FULL_HEADER), ext="txt", base=tmp_path)
    run_metadata("AAPL_10K_2022Q3_2022-10-28", base=tmp_path)
    loaded = load_artifact("metadata", "AAPL_10K_2022Q3_2022-10-28", base=tmp_path)
    assert DocMetadata(**loaded).ticker == "AAPL"       # round-trips into the schema

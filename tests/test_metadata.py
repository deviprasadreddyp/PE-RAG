"""Stage 3 tests: header parsing, header-over-filename precedence, filename backfill, normalization."""

from src.observability import load_artifact, persist_artifact
from src.pipeline.metadata import build_metadata, extract_xbrl_metadata, normalize_form, run_metadata
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
    # B4 fields: stable id, header provenance, curated sector
    assert m.document_id == "AAPL_10K_2022Q3_2022-10-28"
    assert m.source == "SEC EDGAR"
    assert m.industry == "Information Technology"
    assert m.accession_number == "" and not m.is_amended and not m.is_restated


def test_source_defaults_and_industry_unknown_ticker():
    header = "Company: Zzz Corp\nTicker: ZZZ\nFiling Type: 10-K\nFiling Date: 2024-01-01\n"  # no Source
    m = build_metadata("ZZZ_10K_2024-01-01", _raw(header))
    assert m.source == "SEC EDGAR"                       # default when header omits it
    assert m.industry == ""                              # unknown ticker -> never guessed


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


def test_amended_restated_flags_from_header():
    header = (
        "Company: Apple Inc\nTicker: AAPL\nFiling Type: 10-K/A Amended Restated Annual Report\n"
        "Filing Date: 2024-11-01\nAccession Number: 0000320193-24-000123\n"
    )
    m = build_metadata("AAPL_10K_2024-11-01", _raw(header))
    assert m.form == "10-K"
    assert m.accession_number == "0000320193-24-000123"
    assert m.is_amended is True
    assert m.is_restated is True


def test_xbrl_metadata_preserved_from_compact_preamble():
    raw = _raw(
        "Company: Apple Inc\nTicker: AAPL\nFiling Type: 10-Q\nFiling Date: 2022-04-29\n",
        "aapl-20220326false2022Q20000320193--09-24P1Y"
        "UNITED STATES SECURITIES AND EXCHANGE COMMISSION FORM 10-Q\nItem 1. Business\n",
    )
    m = build_metadata("AAPL_10Q_2022Q1_2022-04-29", raw)
    assert m.document_period_end_date == "2022-03-26"
    assert m.report_period == "2022-03-26"
    assert m.document_fiscal_year_focus == 2022
    assert m.document_fiscal_period_focus == "Q2"
    assert m.quarter == "Q2"
    assert m.current_fiscal_year_end_date == "--09-24"
    assert m.amendment_flag is False and m.is_amended is False


def test_xbrl_metadata_preserved_from_xml_tags():
    raw = _raw(
        "Filing Date: 2024-02-01\n",
        "<dei:EntityRegistrantName>Example Co</dei:EntityRegistrantName>"
        "<dei:TradingSymbol>EXM</dei:TradingSymbol>"
        "<dei:DocumentType>10-K</dei:DocumentType>"
        "<dei:DocumentPeriodEndDate>2023-12-31</dei:DocumentPeriodEndDate>"
        "<dei:DocumentFiscalYearFocus>2023</dei:DocumentFiscalYearFocus>"
        "<dei:DocumentFiscalPeriodFocus>FY</dei:DocumentFiscalPeriodFocus>"
        "<dei:AmendmentFlag>true</dei:AmendmentFlag>"
        "<dei:AmendmentDescription>Restated annual report</dei:AmendmentDescription>"
        "UNITED STATES SECURITIES AND EXCHANGE COMMISSION FORM 10-K\n",
    )
    facts = extract_xbrl_metadata(raw)
    assert facts["entity_registrant_name"] == "Example Co"
    assert facts["trading_symbol"] == "EXM"
    assert facts["document_type"] == "10-K"
    assert facts["document_fiscal_year_focus"] == 2023
    assert facts["document_fiscal_period_focus"] == "FY"
    assert facts["amendment_flag"] is True


def test_run_metadata_reads_raw_writes_json(tmp_path):
    persist_artifact("raw", "AAPL_10K_2022Q3_2022-10-28", _raw(FULL_HEADER), ext="txt", base=tmp_path)
    run_metadata("AAPL_10K_2022Q3_2022-10-28", base=tmp_path)
    loaded = load_artifact("metadata", "AAPL_10K_2022Q3_2022-10-28", base=tmp_path)
    assert DocMetadata(**loaded).ticker == "AAPL"       # round-trips into the schema

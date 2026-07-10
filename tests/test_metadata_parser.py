"""Stage 3 tests: company/year/quarter/form/section extraction + cardinality; no false positives."""

from src.reference import match_companies
from src.retrieval.metadata_parser import (
    extract_forms, extract_quarters, extract_section_intent, extract_years, parse_query,
)


def test_company_names_and_order():
    assert match_companies("Compare Apple and Tesla") == ["AAPL", "TSLA"]
    assert match_companies("Tesla vs Apple") == ["TSLA", "AAPL"]        # first-appearance order


def test_uppercase_tickers_matched():
    assert match_companies("AAPL vs MSFT") == ["AAPL", "MSFT"]


def test_common_word_tickers_not_false_matched():
    # "cost"/"cat" as lowercase prose must NOT map to COST/CAT
    assert match_companies("what was the cost of goods") == []
    assert match_companies("the cat sat") == []
    # but the real companies do match
    assert match_companies("Costco and Caterpillar") == ["COST", "CAT"]


def test_msft_not_matched_as_ms():
    assert match_companies("MSFT earnings") == ["MSFT"]                 # not ["MS", "MSFT"]


def test_multiword_and_ampersand_aliases():
    assert match_companies("Johnson & Johnson pipeline") == ["JNJ"]
    assert match_companies("bank of america results") == ["BAC"]


def test_years_quarters_forms():
    assert extract_years("Apple revenue in 2024 and 2022") == [2022, 2024]
    assert extract_quarters("Tesla Q3 and the fourth quarter") == ["Q3", "Q4"]
    assert extract_forms("in the 10-K annual report") == ["10-K"]
    assert extract_forms("latest 10-Q quarterly report") == ["10-Q"]


def test_section_intent():
    assert "Risk Factors" in extract_section_intent("key risks facing Boeing")
    assert "Management's Discussion and Analysis" in extract_section_intent("liquidity and outlook")
    assert "Financial Statements and Supplementary Data" in extract_section_intent("net income and cash flow")
    sections = extract_section_intent("regulatory risks and government investigations")
    assert "Risk Factors" in sections
    assert "Legal Proceedings" in sections
    assert "Management's Discussion and Analysis" in extract_section_intent(
        "growth outlook for user growth and monetization"
    )
    assert "Management's Discussion and Analysis" in extract_section_intent(
        "subscriber and revenue growth"
    )
    assert "Management's Discussion and Analysis" in extract_section_intent(
        "subscription revenue trends"
    )
    assert "Business" in extract_section_intent("membership business model")


def test_parse_query_assembles_full_analysis():
    qa = parse_query("Compare Apple and Tesla risk factors in the 2024 10-K")
    assert qa.companies == ["AAPL", "TSLA"]
    assert qa.years == [2024] and qa.forms == ["10-K"]
    assert "Risk Factors" in qa.section_intent
    assert "risk" in qa.facets
    assert "Comparison" in qa.intents and "MultiCompany" in qa.intents


def test_single_company_cardinality():
    qa = parse_query("What are NVIDIA's risk factors?")
    assert qa.companies == ["NVDA"] and "SingleCompany" in qa.intents


def test_pharma_group_query_expands_to_corpus_companies():
    qa = parse_query("What regulatory risks do the major pharmaceutical companies face?")
    assert qa.companies == ["ABBV", "JNJ", "LLY", "MRK", "PFE"]
    assert "Risk Factors" in qa.section_intent
    assert "Legal Proceedings" in qa.section_intent
    assert "MultiCompany" in qa.intents


def test_business_segments_query_has_facets():
    qa = parse_query("Summarize Amazon's business segments")
    assert "Business" in qa.section_intent
    assert "business" in qa.facets
    assert "segments" in qa.facets

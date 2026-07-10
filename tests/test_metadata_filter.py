"""Stage 4 tests: QueryAnalysis -> HardFilter; section intent is NOT a hard filter."""

from src.retrieval.metadata_filter import build_filter, describe
from src.retrieval.metadata_parser import parse_query
from src.schemas import QueryAnalysis


def test_build_filter_from_parsed_query():
    f = build_filter(parse_query("Apple 2024 10-K risk factors"))
    assert f.tickers == ["AAPL"] and f.years == [2024] and f.forms == ["10-K"]
    assert f.where == {"$and": [
        {"ticker": {"$in": ["AAPL"]}},
        {"year": {"$in": [2024]}},
        {"form": {"$in": ["10-K"]}},
    ]}


def test_year_quarter_filter_also_matches_fiscal_period_alias():
    f = build_filter(parse_query("What legal proceedings does Apple disclose in Q4 2023 10-Q?"))
    assert f.tickers == ["AAPL"]
    assert f.years == [2023]
    assert f.quarters == ["Q4"]
    assert f.forms == ["10-Q"]
    assert f.fiscal_periods == ["2023Q4"]
    assert f.matches({
        "ticker": "AAPL",
        "year": 2024,
        "quarter": "Q1",
        "fiscal_period": "2023Q4",
        "form": "10-Q",
    })
    assert not f.matches({
        "ticker": "AAPL",
        "year": 2024,
        "quarter": "Q1",
        "fiscal_period": "2024Q1",
        "form": "10-Q",
    })


def test_section_intent_is_not_a_hard_filter():
    qa = parse_query("Apple risk factors")           # section intent present, no company constraint beyond AAPL
    f = build_filter(qa)
    assert qa.section_intent == ["Risk Factors"]
    # the filter carries no notion of section — it's company-only here
    assert f.tickers == ["AAPL"] and f.quarters == [] and "section" not in str(f.where)


def test_empty_filter_is_no_op():
    f = build_filter(QueryAnalysis(query="tell me about the company"))
    assert f.is_empty and f.where == {}
    assert describe(f).startswith("(no hard filter")


def test_describe_multi_constraint():
    f = build_filter(parse_query("Compare Apple and Tesla 10-K in 2024"))
    d = describe(f)
    assert "company IN [AAPL, TSLA]" in d and "year IN [2024]" in d and "form IN [10-K]" in d

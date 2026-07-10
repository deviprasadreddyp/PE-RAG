"""Stage 5 tests: query type -> retrieval strategy (per_entity / per_period / global) + boosts."""

from src.config import settings
from src.retrieval.metadata_parser import parse_query
from src.retrieval.retrieval_planner import plan_retrieval


def test_comparison_is_per_entity():
    plan = plan_retrieval(parse_query("Compare Apple and Tesla margins"))
    assert plan.mode == "per_entity"
    assert plan.per_entity_k > 0
    assert plan.pool_size == plan.per_entity_k * 2               # two companies


def test_trend_is_per_period():
    plan = plan_retrieval(parse_query("How has NVIDIA's revenue changed over the years?"))
    assert plan.mode == "per_period"
    assert plan.pool_size == settings.candidate_pool
    assert "Management's Discussion and Analysis" in plan.section_boosts
    assert "Financial Statements and Supplementary Data" in plan.section_boosts


def test_single_risk_is_global_with_risk_boost():
    plan = plan_retrieval(parse_query("What are NVIDIA's risk factors?"))
    assert plan.mode == "global"
    assert plan.section_boosts == ["Risk Factors"]


def test_financial_boosts_when_no_explicit_section():
    plan = plan_retrieval(parse_query("Apple operating results"))
    # "results of operations"/"operating" -> MD&A; ensure a financial section is boosted
    assert any("Management's Discussion" in s or "Financial Statements" in s
               for s in plan.section_boosts)


def test_financial_lookup_boosts_mda_and_financials():
    plan = plan_retrieval(parse_query("What was Alphabet's advertising revenue?"))
    assert "Management's Discussion and Analysis" in plan.section_boosts
    assert "Financial Statements and Supplementary Data" in plan.section_boosts
    assert "financial" in plan.facets


def test_business_segments_boosts_business_and_mda():
    plan = plan_retrieval(parse_query("Summarize Amazon's business segments"))
    assert "Business" in plan.section_boosts
    assert "Management's Discussion and Analysis" in plan.section_boosts
    assert "segments" in plan.facets


def test_general_query_is_global_no_boost():
    plan = plan_retrieval(parse_query("Tell me about the organization"))
    assert plan.mode == "global" and plan.section_boosts == []


def test_multi_company_without_compare_keyword_is_per_entity():
    plan = plan_retrieval(parse_query("AAPL and MSFT cloud strategy"))
    assert plan.mode == "per_entity"

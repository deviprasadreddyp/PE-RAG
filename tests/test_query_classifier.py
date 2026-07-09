"""Stage 2 tests: rule-based multi-label intent classification (the design doc's examples)."""

from src.retrieval.query_classifier import classify


def test_comparison():
    assert "Comparison" in classify("Compare Apple and Tesla")
    assert "Comparison" in classify("Apple versus Microsoft profitability")


def test_trend():
    assert "Trend" in classify("How has NVIDIA's revenue changed?")
    assert "Trend" in classify("Describe the growth trajectory of AMD")


def test_risk():
    assert "Risk" in classify("Primary risks facing JPMorgan")
    assert "Risk" in classify("What are the key headwinds for Boeing?")


def test_financial():
    labels = classify("What was Apple's operating margin and net income?")
    assert "Financial" in labels


def test_temporal_from_year_quarter_and_phrase():
    assert "Temporal" in classify("Apple revenue in 2024")
    assert "Temporal" in classify("Tesla deliveries in Q3")
    assert "Temporal" in classify("NVIDIA revenue over the last two years")


def test_multi_label():
    labels = classify("How has NVIDIA's revenue changed over the last two years?")
    assert {"Trend", "Financial", "Temporal"} <= set(labels)


def test_general_fallback():
    assert classify("Tell me about the company") == ["General"]


def test_labels_are_in_canonical_order():
    labels = classify("Compare Apple and Tesla risk and revenue in 2024")
    # Comparison < Risk < Financial < Temporal in canonical order
    assert labels == sorted(labels, key=lambda x: ["Comparison", "Trend", "Risk", "Financial", "Temporal"].index(x))

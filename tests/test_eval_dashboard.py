"""EV5 tests: eval dashboard helpers + import smoke."""

import pytest

pytest.importorskip("streamlit")

from src.eval import dashboard  # noqa: E402


def test_render_is_callable():
    assert callable(dashboard.render)


def _report():
    return {
        "retrieval": {
            "summary": {"n_cases": 3, "precision@k": 0.5, "mrr": 0.4, "ndcg@k": 0.45},
            "cases": [
                {"id": "q1", "question": "Apple risk", "refused": False, "precision@k": 1.0},
                {"id": "q2", "question": "Tesla risk", "refused": True, "refusal_correct": 1.0},
                {"id": "q3", "question": "Microsoft revenue", "refused": True},
            ],
        },
        "ab": {
            "summary": {
                "bm25": {"recall@k": 0.2, "precision@k": 0.3},
                "hybrid": {"recall@k": 0.6, "precision@k": 0.5},
            }
        },
        "ragas": {"summary": {"faithfulness": 0.9}},
    }


def test_metric_cards_include_counts_and_headlines():
    cards = dashboard.metric_cards(_report())
    assert cards["cases"] == 3
    assert cards["answered"] == 1
    assert cards["refused"] == 2
    assert cards["precision@k"] == 0.5
    assert cards["hybrid recall@k"] == 0.6
    assert cards["faithfulness"] == 0.9


def test_ab_summary_rows_and_chart_frame():
    rows = dashboard.ab_summary_rows(_report())
    assert rows[0]["strategy"] == "bm25"
    frame = dashboard.ab_chart_frame(_report(), "recall@k")
    assert frame.loc["hybrid", "recall@k"] == 0.6


def test_case_rows_and_filters():
    rows = dashboard.case_rows(_report())
    assert rows[0]["status"] == "answered"
    assert rows[1]["status"] == "refused"
    assert [r["id"] for r in dashboard.filter_cases(rows, query="risk", status="refused")] == ["q2"]
    assert [r["id"] for r in dashboard.filter_cases(rows, query="microsoft")] == ["q3"]


def test_case_by_id_and_regression_rows():
    report = _report()
    report["regression"] = {"regressions": [{"metric": "mrr"}], "improvements": []}
    assert dashboard.case_by_id(report)["q1"]["question"] == "Apple risk"
    assert dashboard.regression_rows(report, "regressions") == [{"metric": "mrr"}]

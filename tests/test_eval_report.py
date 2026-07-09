"""EV4 tests: report assembly, regression comparison, JSON+HTML writing (all pure, no index/keys)."""

import json

from src.eval.report import (
    build_html_report, compare_to_previous, flat_summary, load_previous, write_reports,
)
from src.eval.run_eval import assemble_report


def _report():
    rows = [{"id": "q1", "question": "Apple risk", "precision@k": 0.75, "mrr": 1.0, "ndcg@k": 0.9,
             "company_recall": 1.0, "refused": False}]
    ab = {"summary": {"bm25": {"recall@k": 0.6}, "vector": {"recall@k": 0.7}, "hybrid": {"recall@k": 0.9}}}
    ragas = {"summary": {"faithfulness": 0.95, "answer_relevancy": 0.9}}
    return assemble_report(rows, ab=ab, ragas=ragas)


def test_assemble_report_shape():
    r = _report()
    assert r["retrieval"]["summary"]["n_cases"] == 1
    assert r["ab"]["summary"]["hybrid"]["recall@k"] == 0.9
    assert r["ragas"]["summary"]["faithfulness"] == 0.95


def test_flat_summary_namespaces():
    flat = flat_summary(_report())
    assert "precision@k" in flat
    assert flat["ab.hybrid.recall@k"] == 0.9
    assert flat["ragas.faithfulness"] == 0.95


def test_compare_flags_regression_and_improvement():
    prev = {"precision@k": 0.80, "ab.hybrid.recall@k": 0.90}
    cur = {"precision@k": 0.60, "ab.hybrid.recall@k": 0.95}       # precision dropped, recall improved
    cmp = compare_to_previous(cur, prev)
    assert not cmp["ok"]
    assert cmp["regressions"][0]["metric"] == "precision@k"
    assert cmp["improvements"][0]["metric"] == "ab.hybrid.recall@k"


def test_compare_ok_within_tolerance():
    cmp = compare_to_previous({"mrr": 0.90}, {"mrr": 0.91})       # within 0.02 tolerance
    assert cmp["ok"] and not cmp["regressions"]


def test_build_html_contains_sections():
    h = build_html_report(_report())
    assert "<h1>PE-RAG" in h and "Retrieval A/B" in h and "RAGAS" in h and "hybrid" in h


def test_write_and_load_reports(tmp_path):
    paths = write_reports(_report(), tmp_path)
    assert paths["json"].endswith("eval_report.json") and paths["html"].endswith(".html")
    loaded = load_previous(tmp_path)
    assert loaded["ab"]["summary"]["hybrid"]["recall@k"] == 0.9
    assert "<h1>PE-RAG" in (tmp_path / "eval_report.html").read_text("utf-8")
    assert load_previous(tmp_path / "nonexistent") is None

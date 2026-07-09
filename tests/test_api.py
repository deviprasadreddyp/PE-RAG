"""P19 tests: FastAPI /query and /health via TestClient, with run_query stubbed (no network)."""

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient  # noqa: E402

from src.api import main  # noqa: E402
from src.retrieval.retrieval_pipeline import PipelineResult  # noqa: E402
from src.schemas import Answer, Citation, GuardrailResult  # noqa: E402

client = TestClient(main.app)


def _ok_result():
    return PipelineResult(
        answer=Answer(answer="## Executive Summary\nApple faces supply risk [E1].",
                      sources=[Citation(tag="[AAPL 10-K FY2024 · Risk Factors]", ticker="AAPL",
                                        section="Risk Factors")],
                      usage={"input_tokens": 100, "output_tokens": 50}),
        guardrail=GuardrailResult(ok=True, action="accept", confidence="High"),
        refused=False,
        trace={"query": "Apple risk", "plan": "global", "evidence_ids": ["AAPL_c0"]},
    )


def _refusal_result():
    return PipelineResult(answer=Answer(answer="Information unavailable in the provided filings."),
                          refused=True, trace={"query": "x"})


def test_health(monkeypatch):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and "chunks" in body and "bm25" in body


def test_query_happy(monkeypatch):
    monkeypatch.setattr(main, "run_query", lambda q, **kw: _ok_result())
    r = client.post("/query", json={"question": "What are Apple's risk factors?"})
    assert r.status_code == 200
    body = r.json()
    assert not body["refused"] and body["confidence"] == "High"
    assert body["citations"][0]["ticker"] == "AAPL"
    assert body["trace"] is None                       # debug defaults off


def test_query_debug_returns_trace(monkeypatch):
    monkeypatch.setattr(main, "run_query", lambda q, **kw: _ok_result())
    r = client.post("/query", json={"question": "Apple risk", "debug": True})
    assert r.json()["trace"]["plan"] == "global"


def test_query_refusal(monkeypatch):
    monkeypatch.setattr(main, "run_query", lambda q, **kw: _refusal_result())
    r = client.post("/query", json={"question": "compare the leading automakers"})
    body = r.json()
    assert body["refused"] and "Information unavailable" in body["answer"]


def test_empty_question_is_422():
    r = client.post("/query", json={"question": ""})
    assert r.status_code == 422                         # schema validation (min_length=1)

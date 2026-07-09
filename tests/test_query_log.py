"""Stage 17 tests: query-log record shape, cost calc, JSONL append, run_query integration."""

import json

from src.retrieval import query_log
from src.retrieval.query_log import build_log_record, cost_usd, write_log
from src.retrieval.retrieval_pipeline import PipelineResult, run_query
from src.schemas import Answer, GuardrailResult


def _result(refused=False):
    return PipelineResult(
        answer=Answer(answer="ok", usage={"input_tokens": 1000, "output_tokens": 500}),
        guardrail=GuardrailResult(ok=True, action="accept", confidence="High"),
        refused=refused,
        trace={"query": "Apple risk", "intents": ["Risk", "SingleCompany"], "companies": ["AAPL"],
               "plan": "global", "vector_ids": ["a"], "bm25_ids": ["a"], "rrf_ids": ["a"],
               "evidence_ids": ["a"], "prompt_version": "v1",
               "guardrail": {"ok": True, "action": "accept", "confidence": "High"}},
    )


def test_cost_calc_openrouter_pricing():
    # gpt-4o via OpenRouter: 1M input @ $2.5 + 1M output @ $10 = $12.5
    assert cost_usd({"input_tokens": 1_000_000, "output_tokens": 1_000_000}) == 12.5
    assert cost_usd({}) == 0.0


def test_build_log_record_fields():
    rec = build_log_record(_result(), latency_s=1.2345, usage={"input_tokens": 1000, "output_tokens": 500})
    assert rec["query"] == "Apple risk" and rec["plan"] == "global"
    assert rec["confidence"] == "High" and rec["refused"] is False
    assert rec["latency_s"] == 1.2345
    assert rec["input_tokens"] == 1000 and rec["cost_usd"] == cost_usd({"input_tokens": 1000, "output_tokens": 500})
    assert rec["evidence_ids"] == ["a"]


def test_write_log_appends_jsonl(tmp_path):
    write_log({"query": "q1"}, base=tmp_path)
    write_log({"query": "q2"}, base=tmp_path)
    lines = (tmp_path / "logs" / "queries.jsonl").read_text("utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["query"] == "q1" and json.loads(lines[1])["query"] == "q2"


def test_run_query_writes_a_log(tmp_path, monkeypatch):
    # stub answer_query so we don't need retrieval components
    monkeypatch.setattr("src.retrieval.retrieval_pipeline.answer_query", lambda q, **kw: _result())
    run_query("Apple risk", log=True, base=tmp_path)
    lines = (tmp_path / "logs" / "queries.jsonl").read_text("utf-8").strip().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["query"] == "Apple risk"

"""Analyst feedback logging tests."""

import json

from src.retrieval import feedback


def test_feedback_record_captures_trace_fields():
    record = feedback.build_feedback_record(
        question="Compare Apple and Tesla risk factors",
        rating="Needs correction",
        citations_correct=False,
        citation_correction="E2 should cite TSLA Item 1A.",
        comment="Tesla evidence was thin.",
        trace={
            "evidence_ids": ["a", "b"],
            "evidence_used": ["E1", "E2"],
            "prompt_version": "v1",
            "guardrail": {"ok": True},
        },
    )
    assert record["retrieved_ids"] == ["a", "b"]
    assert record["evidence_used"] == ["E1", "E2"]
    assert record["citations_correct"] is False
    assert record["prompt_version"] == "v1"


def test_write_feedback_appends_jsonl(tmp_path):
    record = feedback.build_feedback_record(
        question="Apple risk factors",
        rating="Useful",
        citations_correct=True,
    )
    path = feedback.write_feedback(record, base=tmp_path)
    assert path.name == "feedback.jsonl"
    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    assert rows[0]["question"] == "Apple risk factors"

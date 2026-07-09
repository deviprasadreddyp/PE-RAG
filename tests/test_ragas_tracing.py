"""EV3 tests: RAGAS runner (injectable evaluator, no ragas needed) + LangSmith tracing toggle."""

from pydantic import SecretStr

from src.config import settings
from src.eval import tracing
from src.eval.ragas_runner import RAGAS_METRICS, aggregate_scores, build_samples, ragas_available, run_ragas


def test_build_samples_normalizes_rows():
    rows = [{"question": "Apple revenue?", "answer": "Up [E1].", "contexts": ["net sales rose"]}]
    s = build_samples(rows)
    assert s[0]["question"] == "Apple revenue?" and s[0]["contexts"] == ["net sales rose"]
    assert s[0]["ground_truth"] == ""                         # optional, defaults empty


def test_aggregate_scores_means_and_missing():
    per = [
        {"faithfulness": 1.0, "answer_relevancy": 0.8, "context_precision": 0.9, "context_recall": 0.7},
        {"faithfulness": 0.5, "answer_relevancy": 0.6, "context_precision": 0.7, "context_recall": 0.9},
    ]
    agg = aggregate_scores(per)
    assert agg["faithfulness"] == 0.75 and agg["answer_relevancy"] == 0.7
    assert aggregate_scores([{}])["faithfulness"] is None       # metric never produced


def test_run_ragas_with_injected_evaluator():
    samples = build_samples([{"question": "q", "answer": "a", "contexts": ["c"]}])

    def fake_evaluator(s, metric_names, llm, embeddings):
        assert set(metric_names) == set(RAGAS_METRICS)
        return [{m: 0.9 for m in metric_names}]

    out = run_ragas(samples, evaluator=fake_evaluator)
    assert out["summary"]["faithfulness"] == 0.9 and len(out["per_sample"]) == 1


def test_ragas_available_is_bool():
    assert isinstance(ragas_available(), bool)


def test_enable_langsmith_off_when_no_key(monkeypatch):
    monkeypatch.setattr(settings, "langsmith_api_key", SecretStr(""))
    env: dict = {}
    assert tracing.enable_langsmith(env) is False and env == {}


def test_enable_langsmith_on_with_key(monkeypatch):
    monkeypatch.setattr(settings, "langsmith_api_key", SecretStr("ls-test"))
    env: dict = {}
    assert tracing.enable_langsmith(env) is True
    assert env["LANGSMITH_API_KEY"] == "ls-test"
    assert env["LANGCHAIN_TRACING_V2"] == "true"
    assert env["LANGSMITH_PROJECT"] == settings.langsmith_project

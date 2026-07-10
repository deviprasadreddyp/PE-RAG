"""Generation evaluation with RAGAS (LLM-graded answer quality).

RAGAS scores each answer on the four metrics the design calls for:
- **faithfulness** — is every claim grounded in the retrieved context? (hallucination)
- **answer_relevancy** — does the answer address the question?
- **context_precision** — are the retrieved chunks actually useful / well-ranked?
- **context_recall** — was enough evidence retrieved? (needs a reference answer)

RAGAS itself makes MANY LLM calls — that's fine: this is OFFLINE evaluation, not the production query
path (the one-call rule applies only to answering a user). The grader LLM is our OpenAI model;
embeddings use the configured embedding backend where available. Heavy deps (``ragas``) are lazy; the ``evaluator`` is injectable so the
pipeline glue is unit-testable without ragas installed. Real runs need ``pip install ragas`` + key.
"""

from __future__ import annotations

import importlib.util

from src.config import settings

RAGAS_METRICS = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")


def ragas_available() -> bool:
    return importlib.util.find_spec("ragas") is not None


def build_samples(rows: list[dict]) -> list[dict]:
    """Normalize eval rows into RAGAS samples {question, answer, contexts, ground_truth}."""
    return [
        {
            "question": r["question"],
            "answer": r.get("answer", ""),
            "contexts": list(r.get("contexts") or []),
            "ground_truth": r.get("ground_truth", ""),
        }
        for r in rows
    ]


def aggregate_scores(per_sample: list[dict], metric_names=RAGAS_METRICS) -> dict:
    """Mean of each RAGAS metric across samples (None if a metric was never produced)."""
    agg: dict[str, float | None] = {}
    for m in metric_names:
        vals = [s[m] for s in per_sample if isinstance(s.get(m), (int, float))]
        agg[m] = round(sum(vals) / len(vals), 4) if vals else None
    return agg


def default_llm_and_embeddings():
    """Grader LLM (OpenAI) + configured embeddings for RAGAS (lazy)."""
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model=settings.generation_model, api_key=settings.require_openai_key(),
                     temperature=0)
    embeddings = None
    try:
        from src.pipeline.embed import is_openai_embedding_model
        if is_openai_embedding_model(settings.embedding_model):
            from langchain_openai import OpenAIEmbeddings
            embeddings = OpenAIEmbeddings(model=settings.embedding_model,
                                          api_key=settings.require_openai_key())
        else:
            from langchain_huggingface import HuggingFaceEmbeddings
            embeddings = HuggingFaceEmbeddings(model_name=settings.embedding_model)
    except Exception:  # noqa: BLE001 — embeddings are optional for some metrics
        embeddings = None
    return llm, embeddings


def _default_evaluator(samples, metric_names, llm, embeddings) -> list[dict]:
    """Real RAGAS call (lazy, heavy). Only reached when ragas is installed + keys are set."""
    from ragas import EvaluationDataset, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas import metrics as m

    if llm is None:
        llm, embeddings = default_llm_and_embeddings()
    wrapped_llm = LangchainLLMWrapper(llm)
    wrapped_emb = LangchainEmbeddingsWrapper(embeddings) if embeddings is not None else None

    name_to_metric = {
        "faithfulness": m.Faithfulness(llm=wrapped_llm),
        "answer_relevancy": m.ResponseRelevancy(llm=wrapped_llm, embeddings=wrapped_emb),
        "context_precision": m.LLMContextPrecisionWithoutReference(llm=wrapped_llm),
        "context_recall": m.LLMContextRecall(llm=wrapped_llm),
    }
    chosen = [name_to_metric[n] for n in metric_names if n in name_to_metric]

    ds = EvaluationDataset.from_list([
        {"user_input": s["question"], "response": s["answer"],
         "retrieved_contexts": s["contexts"], "reference": s.get("ground_truth", "")}
        for s in samples
    ])
    result = evaluate(dataset=ds, metrics=chosen)
    return result.to_pandas().to_dict(orient="records")


def run_ragas(samples: list[dict], *, evaluator=None, llm=None, embeddings=None,
              metric_names=RAGAS_METRICS) -> dict:
    """Score samples with RAGAS → {per_sample, summary}. ``evaluator`` is injectable for tests."""
    evaluator = evaluator or _default_evaluator
    per_sample = evaluator(samples, metric_names, llm, embeddings)
    return {"per_sample": per_sample, "summary": aggregate_scores(per_sample, metric_names)}

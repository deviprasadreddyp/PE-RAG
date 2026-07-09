"""Stage 8 — cross-encoder reranking (LOCAL ML; NO API call).

A bi-encoder (vector) retriever has high recall but imprecise ordering. A cross-encoder scores
each (query, chunk) pair jointly for far better precision — locally, with no extra LLM call.

Behind a ``Reranker`` protocol:
- ``CrossEncoderReranker`` — lazy-loads ``sentence_transformers.CrossEncoder`` (default
  ``BAAI/bge-reranker-base``; ``-large`` if latency allows).
- ``IdentityReranker`` — fallback that keeps the incoming (RRF) order.

``get_reranker`` returns the cross-encoder if the package/model is available, else the identity
fallback; the module-level ``rerank`` also degrades to identity if a rerank call fails — so the
pipeline never breaks when the model isn't installed (real reranking is deferred, like the embed/
store runs). Keeps the top ``rerank_top_k`` results.
"""

from __future__ import annotations

from typing import Protocol

from src.config import settings
from src.schemas import RetrievalResult


class Reranker(Protocol):
    def rerank(self, query: str, results: list[RetrievalResult], top_k: int | None = None
               ) -> list[RetrievalResult]: ...


class CrossEncoderReranker:
    """Local cross-encoder (sentence-transformers). Lazy import so the dep stays optional."""

    def __init__(self, model: str | None = None):
        from sentence_transformers import CrossEncoder  # lazy: only when actually reranking

        self.model_name = model or settings.rerank_model
        self._model = CrossEncoder(self.model_name)

    def rerank(self, query, results, top_k=None):
        top_k = top_k or settings.rerank_top_k
        if not results:
            return []
        scores = self._model.predict([(query, r.chunk.text) for r in results])
        ranked = sorted(zip(results, scores), key=lambda rs: float(rs[1]), reverse=True)
        return [RetrievalResult(chunk=r.chunk, score=float(s)) for r, s in ranked[:top_k]]


class IdentityReranker:
    """Fallback: keep the incoming order (already RRF-ranked), just truncate to top_k."""

    def rerank(self, query, results, top_k=None):
        return results[: (top_k or settings.rerank_top_k)]


def get_reranker(model: str | None = None) -> Reranker:
    """CrossEncoderReranker if sentence-transformers + model are available, else IdentityReranker."""
    try:
        return CrossEncoderReranker(model)
    except Exception:  # noqa: BLE001 — missing package or model load failure -> graceful fallback
        return IdentityReranker()


def rerank(query: str, results: list[RetrievalResult], *, reranker: Reranker | None = None,
           top_k: int | None = None) -> list[RetrievalResult]:
    """Rerank ``results`` for ``query``; degrade to RRF order (identity) on any failure."""
    reranker = reranker or get_reranker()
    try:
        return reranker.rerank(query, results, top_k=top_k)
    except Exception:  # noqa: BLE001 — a failed rerank must not break the pipeline
        return IdentityReranker().rerank(query, results, top_k=top_k)

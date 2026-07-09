"""Stage 6b — sparse (BM25) retrieval (deterministic; no LLM).

Query the persisted BM25 index (``data/vectorstore/bm25.json``, built in Stage 8) for lexical
matches — catches exact financial vocabulary (tickers, line items, "10-K") that dense retrieval
can miss. BM25 has no server-side metadata filter, so we over-fetch and apply the ``HardFilter``
predicate in Python.

BM25 stores no document text, so results come back with empty ``chunk.text``; the pipeline
hydrates them via ``vector_retriever.hydrate_texts`` before reranking.
"""

from __future__ import annotations

from src.config import settings
from src.retrieval.vector_retriever import chunk_from_record
from src.schemas import HardFilter, RetrievalResult

_OVERFETCH = 4          # pull extra when filtering, since BM25 filters client-side


def search(query: str, hard_filter: HardFilter, *, index, k: int | None = None
           ) -> list[RetrievalResult]:
    """Lexical search within the hard filter → RetrievalResult list (score = BM25 score)."""
    k = k or settings.bm25_top_k
    fetch = k if hard_filter.is_empty else k * _OVERFETCH
    out: list[RetrievalResult] = []
    for r in index.query(query, k=fetch):
        if not hard_filter.matches(r["metadata"]):
            continue
        # text is unavailable from BM25 — hydrated later from the vector store
        chunk = chunk_from_record({"metadata": r["metadata"], "document": ""})
        out.append(RetrievalResult(chunk=chunk, score=float(r["score"])))
        if len(out) >= k:
            break
    return out

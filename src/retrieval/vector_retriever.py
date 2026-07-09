"""Stage 6a — dense (vector) retrieval (deterministic given the index; no LLM).

Embed the query with the same model used at ingestion (local BAAI/bge-large-en-v1.5, behind the
``Embedder`` protocol — the query gets the bge instruction prefix) and query Chroma within the hard
filter. Cosine distance is converted to a similarity (``1 - distance``). Chroma returns the document
text, so results are fully hydrated ``Chunk`` s.

Also provides ``hydrate_texts`` to fill in text for candidates that came from BM25 (which
stores no document text) — a single ``store.get`` by id.
"""

from __future__ import annotations

from src.config import settings
from src.schemas import Chunk, HardFilter, RetrievalResult


def chunk_from_record(rec: dict) -> Chunk:
    """Reconstruct a Chunk from a Chroma-style record ({id, document, metadata})."""
    md = dict(rec.get("metadata") or {})
    return Chunk(**md, text=rec.get("document", "") or "", embed_text="")


def search(query: str, hard_filter: HardFilter, *, embedder, store, k: int | None = None
           ) -> list[RetrievalResult]:
    """Dense search within the hard filter → RetrievalResult list (score = cosine similarity)."""
    k = k or settings.vector_top_k
    embedding = embedder.embed_query(query)
    where = hard_filter.where or None
    recs = store.query(embedding, k=k, where=where)
    return [
        RetrievalResult(chunk=chunk_from_record(r), score=1.0 - float(r["distance"]))
        for r in recs
    ]


def hydrate_texts(results: list[RetrievalResult], store) -> list[RetrievalResult]:
    """Fill in ``chunk.text`` for any result whose text is empty (e.g. BM25-only), via store.get."""
    missing = [r.chunk.id for r in results if not r.chunk.text]
    if not missing:
        return results
    by_id = {rec["id"]: rec for rec in store.get(missing)}
    for r in results:
        if not r.chunk.text and r.chunk.id in by_id:
            r.chunk = chunk_from_record(by_id[r.chunk.id])
    return results

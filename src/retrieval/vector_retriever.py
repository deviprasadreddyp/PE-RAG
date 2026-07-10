"""Stage 6a — dense (vector) retrieval (deterministic given the index; no LLM).

Embed the query with the same model used at ingestion (behind the ``Embedder`` protocol) and query Chroma within the hard
filter. Cosine distance is converted to a similarity (``1 - distance``). Chroma returns the document
text, so results are fully hydrated ``Chunk`` s.

Also provides ``hydrate_texts`` to fill in text for candidates that came from BM25 (which
stores no document text) — a single ``store.get`` by id.
"""

from __future__ import annotations

from src.config import settings
from src.observability import load_artifact
from src.pipeline.section_resolution import apply_section_resolution
from src.schemas import Chunk, HardFilter, RetrievalResult


def chunk_from_record(rec: dict) -> Chunk:
    """Reconstruct a Chunk from a Chroma-style record ({id, document, metadata})."""
    md = dict(rec.get("metadata") or {})
    chunk = Chunk(**md, text=rec.get("document", "") or "", embed_text="")
    return apply_section_resolution(chunk) if chunk.text else chunk


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
    """Fill in ``chunk.text`` for BM25-only results via Chroma, falling back to chunk artifacts."""
    missing = [r.chunk.id for r in results if not r.chunk.text]
    if not missing:
        return results
    by_id = {rec["id"]: rec for rec in store.get(missing)}
    for r in results:
        if not r.chunk.text and r.chunk.id in by_id:
            r.chunk = chunk_from_record(by_id[r.chunk.id])
        elif not r.chunk.text:
            rec = _load_chunk_record(r.chunk.id)
            if rec:
                r.chunk = chunk_from_record(rec)
    return results


def _load_chunk_record(chunk_id: str) -> dict | None:
    """Hydrate a chunk from persisted ``data/chunks`` when it is not present in Chroma."""
    doc_id = chunk_id.split("__", 1)[0]
    try:
        rows = load_artifact("chunks", doc_id)
    except FileNotFoundError:
        return None
    for row in rows:
        if row.get("id") == chunk_id:
            return {
                "id": chunk_id,
                "document": row.get("text", ""),
                "metadata": {k: v for k, v in row.items() if k not in {"text", "embed_text"}},
            }
    return None

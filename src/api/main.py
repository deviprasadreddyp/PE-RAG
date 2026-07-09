"""FastAPI service — the HTTP surface over the retrieval pipeline (P19).

Endpoints:
- ``POST /query`` — ``{question, debug}`` -> grounded answer + citations (+ stage trace if debug).
- ``GET /health`` — index/store readiness.

The handler calls ``retrieval_pipeline.run_query`` (which times + logs). All heavy components are
constructed lazily inside the pipeline, so importing this module needs no keys or data; a bare
environment degrades to a grounded refusal rather than crashing. FastAPI auto-publishes OpenAPI at
``/docs``. Run:  ``uvicorn src.api.main:app --reload``.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.config import settings
from src.observability import stage_count
from src.pipeline.store import _vectorstore_dir
from src.retrieval.retrieval_pipeline import run_query

app = FastAPI(
    title="PE-RAG",
    version="2.0",
    description="SEC-filings RAG — deterministic retrieval, exactly one grounded Claude call.",
)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=settings.max_query_chars)
    debug: bool = False


class QueryResponse(BaseModel):
    answer: str
    confidence: str = ""
    citations: list[dict] = Field(default_factory=list)
    usage: dict = Field(default_factory=dict)
    refused: bool = False
    trace: dict | None = None


@app.get("/health")
def health() -> dict:
    """Readiness: chunk artifacts present, BM25 built, Chroma reachable (if built)."""
    bm25_ready = (_vectorstore_dir() / "bm25.json").exists()
    chroma_count: int | None = None
    if bm25_ready:                                      # only touch Chroma once an index exists
        try:
            from src.pipeline.store import ChromaVectorStore
            chroma_count = ChromaVectorStore().count()
        except Exception:  # noqa: BLE001 — health must never raise
            chroma_count = None
    return {"status": "ok", "chunks": stage_count("chunks"), "bm25": bm25_ready,
            "chroma": chroma_count}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    """Answer a question over the filings; ``debug=true`` also returns the full stage trace."""
    result = run_query(req.question)
    return QueryResponse(
        answer=result.answer.answer,
        confidence=result.guardrail.confidence if result.guardrail else "",
        citations=[c.model_dump() for c in result.answer.sources],
        usage=result.answer.usage,
        refused=result.refused,
        trace=result.trace if req.debug else None,
    )

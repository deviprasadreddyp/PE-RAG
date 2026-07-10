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

import json
import threading
import time
from queue import Empty, Queue
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import settings
from src.observability import stage_count
from src.pipeline.store import _vectorstore_dir
from src.retrieval.response_parser import REFUSAL
from src.retrieval.retrieval_pipeline import run_query

WEB_DIR = Path(__file__).resolve().parents[1] / "frontend" / "web"
STREAM_STEPS = [
    "Parsing the question",
    "Applying metadata filters",
    "Running hybrid retrieval",
    "Reranking evidence",
    "Building cited context",
    "Making the single LLM call",
    "Resolving source citations",
]

app = FastAPI(
    title="PE-RAG",
    version="2.0",
    description="SEC-filings RAG: deterministic retrieval, exactly one grounded LLM call.",
)
app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")


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


def _query_response(req: QueryRequest) -> QueryResponse:
    try:
        result = run_query(req.question)
    except Exception as exc:  # noqa: BLE001 - public API fails closed with a safe refusal
        safe_trace = {
            "stage": "api_fallback",
            "error_type": type(exc).__name__,
            "message": "The request was refused after an internal pipeline failure.",
        }
        return QueryResponse(
            answer=(
                f"{REFUSAL}\n\n"
                "The system could not safely complete the request. Ask about covered SEC filings, "
                "company risks, financials, MD&A, legal proceedings, or business performance."
            ),
            confidence="Low",
            citations=[],
            usage={},
            refused=True,
            trace=safe_trace if req.debug else None,
        )
    return QueryResponse(
        answer=result.answer.answer,
        confidence=result.guardrail.confidence if result.guardrail else "",
        citations=[c.model_dump() for c in result.answer.sources],
        usage=result.answer.usage,
        refused=result.refused,
        trace=result.trace if req.debug else None,
    )


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _stream_text_chunks(text: str, *, size: int = 42):
    for start in range(0, len(text), size):
        yield text[start:start + size]


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    """Serve the no-build Gemini-style analyst UI."""
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    """Readiness: chunk artifacts present, BM25 built, Chroma reachable (if built)."""
    bm25_ready = (_vectorstore_dir() / "bm25.json").exists()
    chroma_count: int | None = None
    if bm25_ready:                                      # only touch Chroma once an index exists
        try:
            from src.pipeline.store import ChromaVectorStore
            chroma_count = ChromaVectorStore().count()
        except BaseException:  # noqa: BLE001 - health must never raise, including Chroma Rust panics
            chroma_count = None
    return {"status": "ok", "chunks": stage_count("chunks"), "bm25": bm25_ready,
            "chroma": chroma_count}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    """Answer a question over the filings; ``debug=true`` also returns the full stage trace."""
    return _query_response(req)


@app.post("/query-stream", include_in_schema=False)
def query_stream(req: QueryRequest) -> StreamingResponse:
    """Stream progress events, then the final structured answer payload."""

    def events():
        out: Queue[dict | None] = Queue()

        def work() -> None:
            try:
                response = _query_response(req)
                payload = response.model_dump()
                answer = payload.get("answer") or ""
                out.put({"type": "answer_start", "refused": payload.get("refused", False)})
                for chunk in _stream_text_chunks(answer):
                    out.put({"type": "answer_delta", "text": chunk})
                    time.sleep(0.026)
                out.put({"type": "done", "payload": payload})
            except BaseException as exc:  # noqa: BLE001 - stream should surface failures as events
                out.put({"type": "error", "message": str(exc)})
            finally:
                out.put(None)

        threading.Thread(target=work, daemon=True).start()
        step = 0
        while True:
            try:
                item = out.get(timeout=0.75)
            except Empty:
                yield _sse({
                    "type": "progress",
                    "message": STREAM_STEPS[min(step, len(STREAM_STEPS) - 1)],
                    "step": min(step, len(STREAM_STEPS) - 1),
                    "total": len(STREAM_STEPS),
                })
                step += 1
                continue
            if item is None:
                break
            yield _sse(item)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

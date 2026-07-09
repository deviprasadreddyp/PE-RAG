"""Stage 7 — embedding generation.

Embed each chunk's ``embed_text`` (the enriched text from Stage 6) with an
``Embedder`` (default: LangChain ``OpenAIEmbeddings(text-embedding-3-large)``).
Only cache-misses are sent to the provider, in one batched call; every vector is
cached by ``sha256(model + embed_text)`` under ``data/.embedding_cache/`` so
re-runs (and identical chunks across filings) are never re-embedded. Persist
``{chunk_id, embedding, metadata}`` per document to ``data/embeddings/<doc_id>.json``.

The API key is read from config/env only when a real ``OpenAIEmbedder`` is
constructed — importing this module never requires a key or the openai package.

Run standalone:  python -m src.pipeline.embed   (needs OPENAI_API_KEY)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

from src.config import settings
from src.observability import list_artifacts, load_artifact, persist_artifact, run_docs
from src.schemas import Chunk, EmbeddingRecord


class Embedder(Protocol):
    """Swappable embedding backend (OpenAI by default; Voyage/local are alternatives)."""

    model: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class OpenAIEmbedder:
    """LangChain OpenAIEmbeddings wrapper (text-embedding-3-large by default)."""

    def __init__(self, model: str | None = None, api_key: str | None = None):
        from langchain_openai import OpenAIEmbeddings  # lazy: only when actually embedding

        self.model = model or settings.embedding_model
        # Explicit batch size + retries (OpenAI SDK applies exponential backoff on 429/5xx).
        self._client = OpenAIEmbeddings(
            model=self.model,
            api_key=api_key or settings.require_openai_key(),
            chunk_size=settings.embed_batch_size,
            max_retries=settings.embed_max_retries,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._client.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._client.embed_query(text)


def cache_key(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\n{text}".encode("utf-8")).hexdigest()


class EmbeddingCache:
    """Content-addressed vector cache: one file per sha256(model+text)."""

    def __init__(self, base=None):
        self.dir = (Path(base) if base is not None else settings.data_path) / ".embedding_cache"

    def get(self, key: str) -> list[float] | None:
        p = self.dir / f"{key}.json"
        return json.loads(p.read_text("utf-8")) if p.exists() else None

    def put(self, key: str, vector: list[float]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{key}.json").write_text(json.dumps(vector), encoding="utf-8")


def embed_texts(texts: list[str], embedder: Embedder, cache: EmbeddingCache) -> list[list[float]]:
    """Return a vector per text, embedding only cache-misses in a single batched call."""
    keys = [cache_key(embedder.model, t) for t in texts]
    out: list[list[float] | None] = [cache.get(k) for k in keys]
    miss = [i for i, v in enumerate(out) if v is None]
    if miss:
        vectors = embedder.embed_documents([texts[i] for i in miss])   # batched by the embedder
        for i, vec in zip(miss, vectors):
            out[i] = vec
            cache.put(keys[i], vec)
    return out  # type: ignore[return-value]


def run_embed(doc_id: str, *, embedder: Embedder | None = None, base=None) -> dict:
    embedder = embedder or OpenAIEmbedder()
    cache = EmbeddingCache(base=base)
    chunks = [Chunk(**c) for c in load_artifact("chunks", doc_id, base=base)]
    texts = [c.embed_text or c.text for c in chunks]                   # embed the enriched text
    vectors = embed_texts(texts, embedder, cache)
    records = [
        EmbeddingRecord(chunk_id=c.id, embedding=v, metadata=c.metadata())
        for c, v in zip(chunks, vectors)
    ]
    persist_artifact("embeddings", doc_id, records, base=base)
    return {"doc_id": doc_id, "count": len(records),
            "dim": len(records[0].embedding) if records else 0}


def run_all(*, embedder: Embedder | None = None, base=None) -> dict:
    embedder = embedder or OpenAIEmbedder()                            # construct once (fail fast on key/deps)
    r = run_docs("embed", list_artifacts("chunks", base=base),
                 lambda d: run_embed(d, embedder=embedder, base=base), base=base)
    return {"files": r["ok"], "failed": r["failed"],
            "chunks": sum(x["count"] for x in r["results"]),
            "dim": r["results"][0]["dim"] if r["results"] else 0}


if __name__ == "__main__":
    try:
        r = run_all()
    except ImportError:                                               # langchain-openai not installed
        print("Stage 7 embed: install deps first (pip install -r requirements.txt).")
    except RuntimeError as exc:                                       # e.g. missing OPENAI_API_KEY
        print(f"Stage 7 embed: {exc}")
    else:
        print(f"Stage 7 embed: {r['chunks']:,} chunks embedded across {r['files']} files "
              f"(dim {r['dim']}).")

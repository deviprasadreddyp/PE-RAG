"""Stage 7 — embedding generation.

Embed each chunk's ``embed_text`` (the enriched text from Stage 6) with an ``Embedder``
(default: OpenAI ``text-embedding-3-large``; local BGE remains swappable). Only cache-misses are encoded; every vector is cached by
``sha256(model + embed_text)`` under ``data/.embedding_cache/`` so re-runs (and identical chunks
across filings) are never re-embedded. Persist ``{chunk_id, embedding, metadata}`` per document to
``data/embeddings/<doc_id>.json``.

Providers are loaded lazily only when a real embedder is constructed; importing this module never
requires API keys or ``sentence-transformers``.

Run standalone:  python -m src.pipeline.embed
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
    """Swappable embedding backend (local BGE by default; any provider is a drop-in)."""

    model: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


def is_openai_embedding_model(model: str) -> bool:
    return model.startswith("text-embedding-")


class OpenAIEmbedder:
    """OpenAI embeddings backend using the official SDK."""

    def __init__(self, model: str | None = None):
        from openai import OpenAI  # lazy: tests and non-embedding stages do not need it at import time

        self.model = model or settings.embedding_model
        self._client = OpenAI(
            api_key=settings.require_openai_key(),
            max_retries=settings.embed_max_retries,
            timeout=60,
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), settings.embed_batch_size):
            batch = texts[i:i + settings.embed_batch_size]
            response = self._client.embeddings.create(model=self.model, input=batch)
            data = sorted(response.data, key=lambda item: item.index)
            vectors.extend([item.embedding for item in data])
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(list(texts))

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]


class BgeEmbedder:
    """Local ``BAAI/bge-large-en-v1.5`` via sentence-transformers (no API, cosine-normalized).

    Per the bge-v1.5 retrieval recipe, the QUERY is prefixed with a short instruction while passages
    (documents) get none — this materially improves short-query → passage retrieval.
    """

    QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

    def __init__(self, model: str | None = None):
        from sentence_transformers import SentenceTransformer  # lazy: only when actually embedding

        self.model = model or settings.embedding_model
        self._st = SentenceTransformer(self.model)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vecs = self._st.encode(
            texts, batch_size=settings.embed_batch_size,
            normalize_embeddings=True, show_progress_bar=False, convert_to_numpy=True,
        )
        return [v.tolist() for v in vecs]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(list(texts))

    def embed_query(self, text: str) -> list[float]:
        return self._encode([self.QUERY_INSTRUCTION + text])[0]


def get_embedder(model: str | None = None) -> Embedder:
    """Construct the configured embedder backend."""
    chosen = model or settings.embedding_model
    if is_openai_embedding_model(chosen):
        return OpenAIEmbedder(chosen)
    return BgeEmbedder(chosen)


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
    embedder = embedder or get_embedder()
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
    embedder = embedder or get_embedder()                              # load the model once
    r = run_docs("embed", list_artifacts("chunks", base=base),
                 lambda d: run_embed(d, embedder=embedder, base=base), base=base)
    return {"files": r["ok"], "failed": r["failed"],
            "chunks": sum(x["count"] for x in r["results"]),
            "dim": r["results"][0]["dim"] if r["results"] else 0}


if __name__ == "__main__":
    try:
        r = run_all()
    except ImportError:                                               # sentence-transformers not installed
        print("Stage 7 embed: install the embedder first (pip install sentence-transformers).")
    except RuntimeError as exc:
        print(f"Stage 7 embed: {exc}")
    else:
        print(f"Stage 7 embed: {r['chunks']:,} chunks embedded across {r['files']} files "
              f"(dim {r['dim']}).")

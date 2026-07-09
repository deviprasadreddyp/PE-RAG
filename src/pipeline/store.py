"""Stage 8 — vector store + BM25 index.

Join the Stage-7 embeddings with the Stage-5 chunk text and build the searchable
index: a persistent Chroma collection (precomputed vectors + original document
text + full metadata, upserted by ``chunk_id`` so re-runs are idempotent) plus a
BM25 sparse index over the same texts for hybrid retrieval. Chroma sits behind a
``VectorStore`` protocol. Persisted under ``data/vectorstore/`` (Chroma DB +
``bm25.json``).

Precomputed embeddings are stored directly via ``chromadb`` — the engine
LangChain's Chroma wraps — so the Stage-7 cache/precompute is respected rather
than re-embedding at store time. Deterministic; no LLM.

Run standalone:  python -m src.pipeline.store   (needs data/embeddings from Stage 7)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Protocol

from src.config import settings
from src.observability import list_artifacts, load_artifact

TOKEN = re.compile(r"[a-z0-9]+")
UPSERT_BATCH = 2000


def tokenize(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


def _vectorstore_dir(base=None) -> Path:
    return (Path(base) / "vectorstore") if base is not None else settings.chroma_path


def _clean_meta(m: dict) -> dict:
    # Chroma metadata values must be non-null scalars; drop empty strings (they carry no info).
    return {k: v for k, v in m.items() if v is not None and v != ""}


class VectorStore(Protocol):
    def upsert(self, ids, embeddings, documents, metadatas) -> None: ...
    def count(self) -> int: ...
    def query(self, embedding, k: int = 8, where: dict | None = None) -> list[dict]: ...
    def get(self, ids) -> list[dict]: ...


class ChromaVectorStore:
    def __init__(self, persist_dir=None, collection: str | None = None):
        import chromadb

        path = str(persist_dir if persist_dir is not None else settings.chroma_path)
        Path(path).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=path)
        self._col = self._client.get_or_create_collection(
            name=collection or settings.collection_name, metadata={"hnsw:space": "cosine"}
        )

    def upsert(self, ids, embeddings, documents, metadatas) -> None:
        self._col.upsert(
            ids=list(ids),
            embeddings=list(embeddings),
            documents=list(documents),
            metadatas=[_clean_meta(m) for m in metadatas],
        )

    def count(self) -> int:
        return self._col.count()

    def query(self, embedding, k: int = 8, where: dict | None = None) -> list[dict]:
        res = self._col.query(
            query_embeddings=[list(embedding)], n_results=k, where=where,
            include=["documents", "metadatas", "distances"],
        )
        return [
            {"id": res["ids"][0][i], "document": res["documents"][0][i],
             "metadata": res["metadatas"][0][i], "distance": res["distances"][0][i]}
            for i in range(len(res["ids"][0]))
        ]

    def get(self, ids) -> list[dict]:
        """Fetch documents + metadata by id (used to hydrate BM25-only candidates)."""
        res = self._col.get(ids=list(ids), include=["documents", "metadatas"])
        return [
            {"id": res["ids"][i], "document": res["documents"][i], "metadata": res["metadatas"][i]}
            for i in range(len(res["ids"]))
        ]


class Bm25Index:
    """Sparse BM25 index over chunk texts; persisted as tokens + ids + metadata."""

    def __init__(self, ids: list[str], tokens: list[list[str]], metadatas: list[dict]):
        from rank_bm25 import BM25Okapi

        self.ids = ids
        self.tokens = tokens
        self.metadatas = metadatas
        self._bm25 = BM25Okapi(tokens) if tokens else None

    @classmethod
    def build(cls, ids, texts, metadatas) -> "Bm25Index":
        return cls(ids, [tokenize(t) for t in texts], metadatas)

    def query(self, text: str, k: int = 8) -> list[dict]:
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(tokenize(text))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [
            {"id": self.ids[i], "score": float(scores[i]), "metadata": self.metadatas[i]}
            for i in order if scores[i] > 0
        ]

    def save(self, path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps({"ids": self.ids, "tokens": self.tokens, "metadatas": self.metadatas}),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path) -> "Bm25Index":
        d = json.loads(Path(path).read_text("utf-8"))
        return cls(d["ids"], d["tokens"], d["metadatas"])


def run_store(*, base=None, store: VectorStore | None = None, collection: str | None = None) -> dict:
    vs_dir = _vectorstore_dir(base)
    ids, embs, docs, metas = [], [], [], []
    for doc_id in list_artifacts("embeddings", base=base):
        recs = load_artifact("embeddings", doc_id, base=base)
        text_by_id = {c["id"]: c["text"] for c in load_artifact("chunks", doc_id, base=base)}
        for r in recs:
            ids.append(r["chunk_id"])
            embs.append(r["embedding"])
            docs.append(text_by_id[r["chunk_id"]])
            metas.append(r["metadata"])

    if not ids and store is None:                       # nothing to store — don't create an empty DB
        return {"stored": 0, "bm25": 0}

    store = store or ChromaVectorStore(persist_dir=vs_dir, collection=collection)
    for i in range(0, len(ids), UPSERT_BATCH):          # batch for large corpora
        sl = slice(i, i + UPSERT_BATCH)
        store.upsert(ids[sl], embs[sl], docs[sl], metas[sl])

    Bm25Index.build(ids, docs, metas).save(vs_dir / "bm25.json")
    return {"stored": store.count(), "bm25": len(ids)}


if __name__ == "__main__":
    try:
        r = run_store()
    except ImportError:
        print("Stage 8 store: install deps first (pip install -r requirements.txt).")
    else:
        if r["bm25"] == 0:
            print("Stage 8 store: no data/embeddings — run Stage 7 (embed) first.")
        else:
            print(f"Stage 8 store: {r['stored']} vectors in Chroma, {r['bm25']} in BM25.")

"""Embed every regenerated chunk and rebuild Chroma + BM25 with progress output.

Use after deterministic stages are stable and old ``data/embeddings`` /
``data/vectorstore`` have been cleared:

    python -u scripts/build_full_embeddings.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.observability import list_artifacts, load_artifact  # noqa: E402
from src.pipeline.embed import get_embedder, run_embed  # noqa: E402
from src.pipeline.store import run_store  # noqa: E402


def main() -> int:
    docs = sorted((doc_id, len(load_artifact("chunks", doc_id))) for doc_id in list_artifacts("chunks"))
    total = sum(count for _, count in docs)
    print(f"full_docs={len(docs)} full_chunks={total}", flush=True)

    embedder = get_embedder()
    print(f"embedding_model={embedder.model}", flush=True)

    started = time.perf_counter()
    done = 0
    for i, (doc_id, _) in enumerate(docs, start=1):
        result = run_embed(doc_id, embedder=embedder)
        done += result["count"]
        elapsed = max(time.perf_counter() - started, 0.001)
        rate = done / elapsed
        remaining = (total - done) / rate if rate > 0 else 0
        print(
            f"embedded {i}/{len(docs)} {doc_id} chunks={result['count']} "
            f"done={done}/{total} rate={rate:.1f}/s eta={remaining/60:.1f}m",
            flush=True,
        )

    print("running store", flush=True)
    print(f"store_result={run_store()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

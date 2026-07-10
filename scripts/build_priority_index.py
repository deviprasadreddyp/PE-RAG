"""Build a dense priority index for selected tickers, then rebuild BM25/store.

Usage:
    python -u scripts/build_priority_index.py --tickers AAPL TSLA JPM NVDA PFE
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.observability import list_artifacts, load_artifact
from src.pipeline.embed import get_embedder, run_embed
from src.pipeline.store import run_store


def docs_for_tickers(tickers: set[str]) -> list[tuple[str, int]]:
    docs: list[tuple[str, int]] = []
    for doc_id in list_artifacts("chunks"):
        rows = load_artifact("chunks", doc_id)
        if rows and rows[0].get("ticker") in tickers:
            docs.append((doc_id, len(rows)))
    return sorted(docs)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+", required=True)
    args = parser.parse_args(argv)

    tickers = {t.upper() for t in args.tickers}
    docs = docs_for_tickers(tickers)
    total_chunks = sum(count for _, count in docs)
    print(f"priority_tickers={','.join(sorted(tickers))}", flush=True)
    print(f"priority_docs={len(docs)} priority_chunks={total_chunks}", flush=True)
    for doc_id, count in docs:
        print(f"queued {doc_id} chunks={count}", flush=True)

    embedder = get_embedder()
    print(f"embedding_model={embedder.model}", flush=True)
    done = 0
    for i, (doc_id, _) in enumerate(docs, start=1):
        result = run_embed(doc_id, embedder=embedder)
        done += result["count"]
        print(f"embedded {i}/{len(docs)} {doc_id} chunks={result['count']} done={done}", flush=True)

    print("running store", flush=True)
    print(f"store_result={run_store()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

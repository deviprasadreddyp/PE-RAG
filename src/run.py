"""Pipeline orchestrator — run the offline ingestion stages in order.

    python -m src.run                      # run every stage over the whole corpus
    python -m src.run --stage sections     # run one stage over every doc
    python -m src.run --stage clean --doc-id AAPL_10K_2022Q3_2022-10-28
    python -m src.run --force              # ignore "already current" and redo

Stages run in order: ingest -> clean -> metadata -> sections -> chunk -> enrich
-> embed -> store. Each is idempotent and resumable: a stage is skipped when its
output artifact is already current (newer than its inputs), unless --force.
All stages run locally with no API key (embeddings are the local bge model); ``embed`` just needs
``sentence-transformers`` installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.observability import artifact_path, list_artifacts, load_artifact, persist_artifact, stage_count
from src.pipeline import chunk, clean, embed, enrich, ingest, metadata, sections, store

STAGE_NAMES = ("ingest", "clean", "metadata", "sections", "chunk", "enrich", "embed", "store")


@dataclass
class Stage:
    name: str
    per_doc: bool
    docs: Callable[[], list]          # doc_ids to consider (per-doc); [None] for corpus stages
    current: Callable[[object], bool]  # is this doc's output already up to date?
    run: Callable[[object], object]    # execute for one doc (or the whole corpus)


def run(
    stage: str = "all", *, doc_id: str | None = None, force: bool = False,
    base=None, corpus_dir=None, embedder=None,
) -> dict:
    if stage != "all" and stage not in STAGE_NAMES:
        raise ValueError(f"unknown stage {stage!r}; choose from {(*STAGE_NAMES, 'all')}")

    def art(s, d, ext):
        return artifact_path(s, d, ext, base=base)

    def newer(out, *ins) -> bool:
        if not out.exists():
            return False
        om = out.stat().st_mtime
        return all((not i.exists()) or om >= i.stat().st_mtime for i in ins)

    def enrich_current(d) -> bool:
        p = art("chunks", d, "json")
        if not p.exists():
            return False
        data = load_artifact("chunks", d, base=base)
        return bool(data) and bool(data[0].get("embed_text"))

    _embedder = {"e": embedder}

    def get_embedder():
        if _embedder["e"] is None:
            _embedder["e"] = embed.BgeEmbedder()
        return _embedder["e"]

    raw_docs = lambda: list_artifacts("raw", "txt", base=base)          # noqa: E731
    cleaned_docs = lambda: list_artifacts("cleaned", "txt", base=base)  # noqa: E731
    chunk_docs = lambda: list_artifacts("chunks", "json", base=base)    # noqa: E731

    stages = {
        "ingest": Stage(
            "ingest", False, lambda: [None],
            lambda d: stage_count("raw", "txt", base=base) > 0,
            lambda d: ingest.run_ingest(corpus_dir, base=base)),
        "clean": Stage(
            "clean", True, raw_docs,
            lambda d: newer(art("cleaned", d, "txt"), art("raw", d, "txt")),
            lambda d: clean.run_clean(d, base=base)),
        "metadata": Stage(
            "metadata", True, raw_docs,
            lambda d: newer(art("metadata", d, "json"), art("raw", d, "txt")),
            lambda d: metadata.run_metadata(d, base=base)),
        "sections": Stage(
            "sections", True, cleaned_docs,
            lambda d: newer(art("sections", d, "json"), art("cleaned", d, "txt"),
                            art("metadata", d, "json")),   # sections now canonicalize using form
            lambda d: sections.run_sections(d, base=base)),
        "chunk": Stage(
            "chunk", True, cleaned_docs,
            lambda d: newer(art("chunks", d, "json"), art("cleaned", d, "txt"),
                            art("sections", d, "json"), art("metadata", d, "json")),
            lambda d: chunk.run_chunk(d, base=base)),
        "enrich": Stage(
            "enrich", True, chunk_docs, enrich_current,
            lambda d: enrich.run_enrich(d, base=base)),
        "embed": Stage(
            "embed", True, chunk_docs,
            lambda d: newer(art("embeddings", d, "json"), art("chunks", d, "json")),
            lambda d: embed.run_embed(d, embedder=get_embedder(), base=base)),
        "store": Stage(
            "store", False, lambda: [None],
            lambda d: (store._vectorstore_dir(base) / "bm25.json").exists(),
            lambda d: store.run_store(base=base)),
    }

    selected = STAGE_NAMES if stage == "all" else (stage,)
    report: dict = {}
    for name in selected:
        st = stages[name]
        docs = ([doc_id] if doc_id else st.docs()) if st.per_doc else [None]
        ran = skipped = 0
        failures: list = []
        for d in docs:
            if not force and st.current(d):
                skipped += 1
                continue
            try:
                st.run(d)
                ran += 1
            except (ImportError, RuntimeError):
                raise                                       # deps/key problem — abort; main() reports it
            except Exception as exc:                        # noqa: BLE001 — isolate a bad document
                failures.append({"doc_id": d, "reason": f"{type(exc).__name__}: {exc}"})
        if failures:
            persist_artifact("logs", f"{name}_failures", failures, base=base)
        report[name] = {"ran": ran, "skipped": skipped, "failed": len(failures)}
    return report


def main(argv=None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="python -m src.run", description="PE-RAG ingestion pipeline")
    p.add_argument("--stage", default="all", choices=(*STAGE_NAMES, "all"))
    p.add_argument("--doc-id", default=None)
    p.add_argument("--force", action="store_true")
    args = p.parse_args(argv)
    try:
        report = run(stage=args.stage, doc_id=args.doc_id, force=args.force)
    except ImportError:
        print("Pipeline: install deps first (pip install -r requirements.txt).")
        return 1
    except RuntimeError as exc:
        print(f"Pipeline: {exc}")
        return 1
    for name in STAGE_NAMES:
        if name in report:
            r = report[name]
            print(f"  {name:9} ran {r['ran']:>4}  skipped {r['skipped']:>4}  failed {r.get('failed', 0):>3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

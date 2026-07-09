"""Stage 1 — raw ingestion.

Read ``edgar_corpus/manifest.json`` (the authoritative file list), validate each
file (filename pattern, existence, UTF-8 decodability), and persist it UNCHANGED
to ``data/raw/<doc_id>.txt``. Content is not modified here — XBRL stripping
happens in Stage 2 (cleaning). Failures are collected in
``data/raw/_dead_letter.json`` rather than dropped silently.

Every ingested file is fingerprinted (SHA-256) into ``data/raw_index.json`` — a
typed ``Document`` catalog that powers **incremental indexing**: comparing this
run's hashes against the prior index tells us exactly which filings are new or
changed, so a re-run can re-embed only those (``report["changed"]``).

Run standalone:  python -m src.pipeline.ingest
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import re

from src.config import settings
from src.observability import persist_artifact
from src.schemas import Document

SUFFIX = "_full.txt"

# TICKER_FORM_[PERIOD]_YYYY-MM-DD_full.txt  (PERIOD like 2024Q3 is optional)
FILENAME = re.compile(
    r"^(?P<ticker>[A-Z][A-Z0-9]*)_(?P<form>10K|10Q)_"
    r"(?:(?P<period>\d{4}Q[1-4])_)?(?P<date>\d{4}-\d{2}-\d{2})" + re.escape(SUFFIX) + r"$"
)


def doc_id_for(filename: str) -> str:
    """'AAPL_10K_2022Q3_2022-10-28_full.txt' -> 'AAPL_10K_2022Q3_2022-10-28'."""
    return filename[: -len(SUFFIX)]


def _index_path(base: str | Path | None) -> Path:
    """Location of the corpus catalog (``data/raw_index.json`` by default)."""
    return (Path(base) if base is not None else settings.data_path) / "raw_index.json"


def load_raw_index(base: str | Path | None = None) -> dict[str, str]:
    """Prior ingest catalog as ``{doc_id: sha256}`` ({} if none) — for change detection."""
    p = _index_path(base)
    if not p.exists():
        return {}
    return {d["doc_id"]: d["sha256"] for d in json.loads(p.read_text("utf-8"))}


def run_ingest(
    corpus_dir: str | Path | None = None, *, base: str | Path | None = None
) -> dict:
    """Ingest every manifest file; return {ingested, failed, dead_letter, documents, changed}."""
    corpus = Path(corpus_dir) if corpus_dir is not None else settings.corpus_path
    files = json.loads((corpus / "manifest.json").read_text("utf-8"))["files"]

    prior = load_raw_index(base)                                # hashes from the previous run
    docs: list[Document] = []
    dead: list[dict] = []
    for fname in files:
        if not FILENAME.match(fname):
            dead.append({"file": fname, "reason": "invalid filename"})
            continue
        path = corpus / fname
        if not path.is_file():
            dead.append({"file": fname, "reason": "missing file"})
            continue
        try:
            raw = path.read_text(encoding="utf-8")           # strict: detects bad UTF-8
        except UnicodeDecodeError as exc:
            dead.append({"file": fname, "reason": f"not valid UTF-8: {exc}"})
            continue
        doc_id = doc_id_for(fname)
        persist_artifact("raw", doc_id, raw, ext="txt", base=base)  # unchanged
        docs.append(Document(
            doc_id=doc_id,
            filename=fname,
            sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            size=len(raw),
        ))

    persist_artifact("raw", "_dead_letter", dead, base=base)   # always written (may be [])
    changed = [d.doc_id for d in docs if prior.get(d.doc_id) != d.sha256]  # new or modified
    p = _index_path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([d.model_dump() for d in docs], indent=2), encoding="utf-8")
    return {
        "ingested": len(docs),
        "failed": len(dead),
        "dead_letter": dead,
        "documents": docs,
        "changed": changed,
    }


if __name__ == "__main__":
    report = run_ingest()
    print(f"Stage 1 ingest: {report['ingested']} ingested, {report['failed']} dead-lettered, "
          f"{len(report['changed'])} new/changed since last run.")
    for d in report["dead_letter"]:
        print("  DEAD:", d["file"], "-", d["reason"])

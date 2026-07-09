"""Stage 1 — raw ingestion.

Read ``edgar_corpus/manifest.json`` (the authoritative file list), validate each
file (filename pattern, existence, UTF-8 decodability), and persist it UNCHANGED
to ``data/raw/<doc_id>.txt``. Content is not modified here — XBRL stripping
happens in Stage 2 (cleaning). Failures are collected in
``data/raw/_dead_letter.json`` rather than dropped silently.

Run standalone:  python -m src.pipeline.ingest
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.config import settings
from src.observability import persist_artifact

SUFFIX = "_full.txt"

# TICKER_FORM_[PERIOD]_YYYY-MM-DD_full.txt  (PERIOD like 2024Q3 is optional)
FILENAME = re.compile(
    r"^(?P<ticker>[A-Z][A-Z0-9]*)_(?P<form>10K|10Q)_"
    r"(?:(?P<period>\d{4}Q[1-4])_)?(?P<date>\d{4}-\d{2}-\d{2})" + re.escape(SUFFIX) + r"$"
)


def doc_id_for(filename: str) -> str:
    """'AAPL_10K_2022Q3_2022-10-28_full.txt' -> 'AAPL_10K_2022Q3_2022-10-28'."""
    return filename[: -len(SUFFIX)]


def run_ingest(
    corpus_dir: str | Path | None = None, *, base: str | Path | None = None
) -> dict:
    """Ingest every file listed in the manifest; return {ingested, failed, dead_letter}."""
    corpus = Path(corpus_dir) if corpus_dir is not None else settings.corpus_path
    files = json.loads((corpus / "manifest.json").read_text("utf-8"))["files"]

    ingested = 0
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
        persist_artifact("raw", doc_id_for(fname), raw, ext="txt", base=base)  # unchanged
        ingested += 1

    persist_artifact("raw", "_dead_letter", dead, base=base)   # always written (may be [])
    return {"ingested": ingested, "failed": len(dead), "dead_letter": dead}


if __name__ == "__main__":
    report = run_ingest()
    print(f"Stage 1 ingest: {report['ingested']} ingested, {report['failed']} dead-lettered.")
    for d in report["dead_letter"]:
        print("  DEAD:", d["file"], "-", d["reason"])

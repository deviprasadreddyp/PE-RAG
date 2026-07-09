"""Stage 3 — deterministic metadata extraction (NEVER an LLM).

Build a ``DocMetadata`` from the filing's header block (in ``data/raw/``) plus the
filename. The header wins where both provide a value; the filename backfills what
the header lacks (the corpus is missing ``Report Period`` / ``Quarter`` on ~22% of
files — see architecture/corpus_notes.md). ``form`` is normalized to exactly
``10-K`` / ``10-Q``. Persist to ``data/metadata/<doc_id>.json``.

Run standalone:  python -m src.pipeline.metadata
"""

from __future__ import annotations

import re

from src.observability import list_artifacts, load_artifact, persist_artifact
from src.pipeline.clean import split_header_body
from src.pipeline.ingest import FILENAME, SUFFIX
from src.schemas import DocMetadata


def parse_header(header: str) -> dict[str, str]:
    """Header lines 'Label: value' -> {label: value} (split on the first colon)."""
    out: dict[str, str] = {}
    for line in header.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            if key:
                out[key] = val.strip()
    return out


def parse_filename(doc_id: str) -> dict[str, str]:
    """Pull ticker/form/period/date from the filename (empty dict if it doesn't match)."""
    m = FILENAME.match(doc_id + SUFFIX)
    return {k: (v or "") for k, v in m.groupdict().items()} if m else {}


def normalize_form(text: str) -> str:
    """'10-K (Annual Report)' / '10K' -> '10-K'; '10-Q' / '10Q' -> '10-Q'; else ''."""
    m = re.search(r"10-?\s*([KQ])", text, re.I)
    return f"10-{m.group(1).upper()}" if m else ""


def _quarter(fiscal_period: str) -> str:
    m = re.search(r"Q([1-4])", fiscal_period, re.I)
    return f"Q{m.group(1)}" if m else ""


def _year(*sources: str) -> int:
    for s in sources:
        m = re.search(r"(?:19|20)\d{2}", s or "")
        if m:
            return int(m.group(0))
    return 0


def build_metadata(doc_id: str, raw: str) -> DocMetadata:
    header, _ = split_header_body(raw)
    h = parse_header(header)
    fn = parse_filename(doc_id)

    ticker = h.get("Ticker") or fn.get("ticker", "")
    form = normalize_form(h.get("Filing Type", "")) or normalize_form(fn.get("form", ""))
    filing_date = h.get("Filing Date") or fn.get("date", "")
    report_period = h.get("Report Period", "")
    # The header's "Quarter" field holds a fiscal period like "2022Q3"; backfill from the filename.
    fiscal_period = h.get("Quarter") or fn.get("period", "")
    return DocMetadata(
        company=h.get("Company") or ticker,
        ticker=ticker,
        form=form,
        filing_date=filing_date,
        report_period=report_period,
        fiscal_period=fiscal_period,
        year=_year(fiscal_period, report_period, filing_date),
        quarter=_quarter(fiscal_period),
        cik=h.get("CIK", ""),
        source_url=h.get("URL", ""),
        source_file=doc_id + SUFFIX,
    )


def run_metadata(doc_id: str, *, base=None) -> DocMetadata:
    raw = load_artifact("raw", doc_id, ext="txt", base=base)
    meta = build_metadata(doc_id, raw)
    persist_artifact("metadata", doc_id, meta, base=base)
    return meta


def run_all(*, base=None) -> dict:
    ids = list_artifacts("raw", ext="txt", base=base)
    metas = [run_metadata(i, base=base) for i in ids]
    return {"extracted": len(metas), "metas": metas}


if __name__ == "__main__":
    r = run_all()
    if not r["metas"]:
        print("Stage 3 metadata: no data/raw artifacts — run `python -m src.pipeline.ingest` first.")
    else:
        with_period = sum(1 for m in r["metas"] if m.fiscal_period)
        print(f"Stage 3 metadata: {r['extracted']} filings; "
              f"fiscal_period present on {with_period}/{r['extracted']} after backfill.")

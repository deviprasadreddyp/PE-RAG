"""Stage 6 — chunk enrichment.

Before embedding, prepend each chunk's parent context (company, ticker, filing
type, year, quarter, section) to produce ``embed_text``. This gives the embedding
model richer semantic context while the original ``text`` is preserved verbatim
for display and citations. Deterministic and idempotent — ``embed_text`` is always
derived from ``text``, so re-running never stacks headers. Re-persist in place to
``data/chunks/<doc_id>.json``.

Run standalone:  python -m src.pipeline.enrich
"""

from __future__ import annotations

from src.observability import list_artifacts, load_artifact, persist_artifact, run_docs
from src.schemas import Chunk

SEP = "\n---\n"


def _year(chunk: Chunk) -> str:
    if chunk.year:
        return str(chunk.year)
    if chunk.fiscal_period:
        return chunk.fiscal_period[:4]
    return chunk.filing_date[:4] if chunk.filing_date else ""


def enrich_text(chunk: Chunk) -> str:
    quarter = chunk.quarter or "FY"                  # "FY" for a full-year 10-K (no quarter)
    fiscal_focus = chunk.document_fiscal_period_focus or quarter
    amended = "yes" if chunk.amendment_flag or chunk.is_amended else "no"
    header = (
        f"Company: {chunk.company} ({chunk.ticker}) | Filing: {chunk.form} | "
        f"Year: {_year(chunk)} | Quarter: {quarter} | Fiscal focus: {fiscal_focus} | "
        f"Period end: {chunk.document_period_end_date or chunk.report_period} | "
        f"CIK: {chunk.cik} | Amended: {amended} | Section: {chunk.section}"
    )
    return f"{header}{SEP}{chunk.text}"


def enrich_chunk(chunk: Chunk) -> Chunk:
    # derive from .text (not .embed_text) so re-enriching is idempotent
    return chunk.model_copy(update={"embed_text": enrich_text(chunk)})


def run_enrich(doc_id: str, *, base=None) -> list[Chunk]:
    chunks = [Chunk(**c) for c in load_artifact("chunks", doc_id, base=base)]
    enriched = [enrich_chunk(c) for c in chunks]
    persist_artifact("chunks", doc_id, enriched, base=base)
    return enriched


def run_all(*, base=None) -> dict:
    return run_docs("enrich", list_artifacts("chunks", base=base),
                    lambda d: run_enrich(d, base=base), base=base)


if __name__ == "__main__":
    r = run_all()
    if not r["results"] and not r["failed"]:
        print("Stage 6 enrich: no data/chunks — run `python -m src.pipeline.chunk` first.")
    else:
        enriched = sum(len(v) for v in r["results"])
        print(f"Stage 6 enrich: {enriched:,} chunks enriched across {r['ok']} files ({r['failed']} failed).")

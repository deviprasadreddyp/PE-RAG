"""Stage 2 — cleaning.

Load ``data/raw/<doc_id>.txt``, drop the header block and the leading XBRL/us-gaap
blob (anchoring on the first prose marker), drop residual XBRL tag lines, and
collapse blank-line runs — while PRESERVING business text, section titles,
numbers/units, and table rows (internal spacing is kept). Persist the cleaned
prose to ``data/cleaned/<doc_id>.txt``. Deterministic; no LLM.

Run standalone:  python -m src.pipeline.clean   (cleans everything in data/raw/)
"""

from __future__ import annotations

import re

from src.observability import list_artifacts, load_artifact, persist_artifact, run_docs

SEP = re.compile(r"={10,}")
PROSE = re.compile(r"UNITED STATES\s*SECURITIES AND EXCHANGE COMMISSION|FORM 10-[KQ]", re.I)
# An XBRL context line starts with a CIK-length digit run then a namespace tag, e.g.
# "0000320193us-gaap:CommonStockMember...". Prose never looks like this.
XBRL_LINE = re.compile(r"^\s*\d{6,}(?:us-gaap|srt|dei|country|iso4217|xbrli|utr|[a-z]{1,10}):", re.I)


def split_header_body(raw: str) -> tuple[str, str]:
    """Split on the '====' separator. No separator -> treat the whole thing as body."""
    parts = SEP.split(raw, maxsplit=1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("", raw)


def clean(raw: str) -> str:
    """Raw filing text -> cleaned prose (deterministic)."""
    _, body = split_header_body(raw)
    m = PROSE.search(body)
    prose = body[m.start():] if m else body                       # drop the leading XBRL blob
    prose = "\n".join(ln for ln in prose.split("\n") if not XBRL_LINE.match(ln))  # residual tags
    prose = re.sub(r"[ \t]+\n", "\n", prose)                       # strip trailing spaces
    prose = re.sub(r"\n{3,}", "\n\n", prose)                       # collapse blank-line runs
    return prose.strip() + "\n"


def run_clean(doc_id: str, *, base=None) -> dict:
    raw = load_artifact("raw", doc_id, ext="txt", base=base)
    cleaned = clean(raw)
    persist_artifact("cleaned", doc_id, cleaned, ext="txt", base=base)
    return {"doc_id": doc_id, "raw_chars": len(raw), "cleaned_chars": len(cleaned)}


def run_all(*, base=None) -> dict:
    return run_docs("clean", list_artifacts("raw", "txt", base=base),
                    lambda d: run_clean(d, base=base), base=base)


if __name__ == "__main__":
    r = run_all()
    if not r["results"] and not r["failed"]:
        print("Stage 2 clean: no data/raw artifacts found — run `python -m src.pipeline.ingest` first.")
    else:
        raw_tot = sum(x["raw_chars"] for x in r["results"])
        cln_tot = sum(x["cleaned_chars"] for x in r["results"])
        print(f"Stage 2 clean: {r['ok']} cleaned, {r['failed']} failed; "
              f"{raw_tot:,} -> {cln_tot:,} chars ({100 * cln_tot // max(raw_tot, 1)}% retained).")

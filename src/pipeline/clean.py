"""Stage 2 — controlled normalization (NOT structural parsing).

Cosmetic, content-preserving normalization of a raw filing. It:
  - normalizes newlines (CRLF -> LF) and whitespace (tabs -> spaces; collapses
    multi-space in prose only — tables / aligned columns are preserved),
  - collapses excessive blank-line runs,
  - performs a *controlled* XBRL trim that removes ONLY the leading machine-data
    prefix (the blob shares a line with the cover page, so we cut at the first
    prose marker) plus residual isolated XBRL tag lines.

It never deletes business text, tables, numbers, or headings. Structural
understanding (metadata, sections) is a *separate* concern handled in Stages 3-4
— this is the Normalization vs Structural Parsing split. Persist to
``data/cleaned/<doc_id>.txt``. Deterministic; no LLM.

Run standalone:  python -m src.pipeline.clean
"""

from __future__ import annotations

import re

from src.observability import list_artifacts, load_artifact, persist_artifact, run_docs

SEP = re.compile(r"={10,}")
PROSE = re.compile(r"UNITED STATES\s*SECURITIES AND EXCHANGE COMMISSION|FORM 10-[KQ]", re.I)
# An XBRL context line starts with a CIK-length digit run then a namespace tag, e.g.
# "0000320193us-gaap:CommonStockMember...". Prose never looks like this.
XBRL_LINE = re.compile(r"^\s*\d{6,}(?:us-gaap|srt|dei|country|iso4217|xbrli|utr|[a-z]{1,10}):", re.I)
XML_DECL = re.compile(r"<\?xml\b.*?\?>|<!DOCTYPE\b.*?>", re.I | re.S)
XBRL_WRAPPER = re.compile(r"</?(?:[A-Za-z0-9_-]+:)?xbrl\b[^>]*>", re.I)
XBRL_REF = re.compile(
    r"<(?:[A-Za-z0-9_-]+:)?(?:schemaRef|roleRef|arcroleRef|linkbaseRef)\b[^>]*/?>",
    re.I,
)
XBRL_BLOCK = re.compile(
    r"<(?:[A-Za-z0-9_-]+:)?(?:context|unit)\b.*?</(?:[A-Za-z0-9_-]+:)?(?:context|unit)>",
    re.I | re.S,
)
XMLNS_ATTR = re.compile(r"\s+xmlns(?::[A-Za-z0-9_-]+)?=\"[^\"]*\"", re.I)
PARSER_ATTR = re.compile(r"\s+(?:contextRef|unitRef|decimals|precision|id)=\"[^\"]*\"", re.I)
XML_INFRA_LINE = re.compile(
    r"^\s*(?:<\?xml|<!DOCTYPE|</?(?:[A-Za-z0-9_-]+:)?xbrl\b|xmlns:|"
    r"<(?:[A-Za-z0-9_-]+:)?(?:schemaRef|roleRef|arcroleRef|linkbaseRef|context|unit)\b)",
    re.I,
)


def split_header_body(raw: str) -> tuple[str, str]:
    """Split on the '====' separator. No separator -> treat the whole thing as body."""
    parts = SEP.split(raw, maxsplit=1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("", raw)


def _is_tabular(line: str) -> bool:
    """Preserve spacing on tables/signatures/aligned columns."""
    return "|" in line or "/s/" in line or len(re.findall(r"\S {2,}\S", line)) >= 2


def _normalize_line(line: str) -> str:
    line = line.replace("\t", " ").rstrip()          # tabs -> space; drop trailing spaces
    if _is_tabular(line):
        return line                                  # keep table / column alignment intact
    return re.sub(r" {2,}", " ", line)               # collapse multi-space in prose only


def _strip_xbrl_infrastructure(text: str) -> str:
    """Remove parser plumbing while leaving narrative/table text intact."""
    text = XML_DECL.sub("", text)
    text = XBRL_BLOCK.sub("", text)                   # context/unit definitions are parser-only
    text = XBRL_REF.sub("", text)
    text = XBRL_WRAPPER.sub("", text)
    text = XMLNS_ATTR.sub("", text)
    text = PARSER_ATTR.sub("", text)
    return text


def clean(raw: str) -> str:
    """Raw filing text -> normalized prose (controlled; content-preserving)."""
    _, body = split_header_body(raw)
    body = body.replace("\r\n", "\n").replace("\r", "\n")            # CRLF -> LF
    m = PROSE.search(body)
    body = body[m.start():] if m else body                          # controlled boundary trim (prefix only)
    body = _strip_xbrl_infrastructure(body)
    lines = [
        _normalize_line(ln)
        for ln in body.split("\n")
        if not XBRL_LINE.match(ln) and not XML_INFRA_LINE.match(ln)
    ]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))              # collapse blank-line runs
    return text.strip() + "\n"


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

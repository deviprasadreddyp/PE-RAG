"""Stage 4 — section detection (deterministic; no LLM).

SEC filings render section headings inline (not at line starts) as
``Item 7A.\xa0\xa0\xa0\xa0Quantitative ...`` — the item number and period followed by a
Title-Cased heading. Cross-references ("... described in Item 1A of Part I ...")
and table-of-contents rows ("Item 1. | Business | 5") do NOT have that shape, so
we detect a real heading as ``Item N[A][.] <UpperCaseTitle>`` and exclude
cross-references by the preceding word ("see/of/in/under ..."). Titles bleed into
the body with no delimiter, so we cut the title at the first camelCase seam
(``FactorsThe`` -> ``Factors``).

Detected headings that begin a substantial body become contiguous
``SectionSpan`` s; the cover page + TOC before the first heading is bucketed as
"Other". If nothing is detected, the whole document is a single "Other" span so
chunking still works. Spans always cover the whole document.

Persist to ``data/sections/<doc_id>.json``.  Run standalone:  python -m src.pipeline.sections
"""

from __future__ import annotations

import re

from src.observability import list_artifacts, load_artifact, persist_artifact
from src.schemas import SectionSpan

# "Item" (opt nbsp) number+letter, opt '.'/')' , spaces/nbsp/pipe, then an Upper-cased title.
# The pipe allows the "Item 1. | Financial Statements" layout some 10-Qs use.
HEAD = re.compile(r"Item[ \t\xa0]*(\d+[A-Za-z]?)[.)]?[ \t\xa0|]+([A-Z][^\n\xa0|]{2,70})")
MIN_SECTION_CHARS = 500          # a real section has a substantial body
# words that, immediately before "Item", mark a cross-reference rather than a heading
_CONNECTORS = {
    "see", "of", "in", "under", "to", "and", "the", "or", "within", "below",
    "above", "from", "per", "with", "by", "this", "our", "such",
}


def _norm_item(raw: str) -> str:
    m = re.match(r"(\d+)([A-Za-z]?)", raw)
    return f"Item {int(m.group(1))}{m.group(2).upper()}" if m else f"Item {raw}"


def _clean_title(raw: str) -> str:
    t = re.split(r"(?<=[a-z])(?=[A-Z])", raw, maxsplit=1)[0]     # cut camelCase bleed into body
    t = re.sub(r"\s+", " ", t.replace("|", " ")).strip(" .:-)")
    t = re.sub(r"\s*\d+$", "", t).strip()                        # drop trailing page number
    return t if len(t) >= 3 and not t.isdigit() else ""


def _is_crossref(text: str, start: int) -> bool:
    toks = re.findall(r"[A-Za-z]+", text[max(0, start - 20):start])
    return bool(toks) and toks[-1].lower() in _CONNECTORS


def detect_sections(text: str) -> list[SectionSpan]:
    n = len(text)
    if n == 0:
        return []
    cands = [
        (m.start(), _norm_item(m.group(1)), _clean_title(m.group(2)))
        for m in HEAD.finditer(text)
        if not _is_crossref(text, m.start())
    ]
    kept = [
        (pos, item, title)
        for i, (pos, item, title) in enumerate(cands)
        if (cands[i + 1][0] if i + 1 < len(cands) else n) - pos >= MIN_SECTION_CHARS
    ]
    # Collapse consecutive repeats of the same item (per-page header reprints).
    collapsed: list[tuple[int, str, str]] = []
    for c in kept:
        if not collapsed or collapsed[-1][1] != c[1]:
            collapsed.append(c)
    kept = collapsed

    # Drop a leading stray (a high-numbered TOC-tail entry before the real start):
    # the body begins at the first lowest-numbered item; earlier entries fold into "Other".
    if kept:
        nums = [int(re.match(r"Item (\d+)", it).group(1)) for _, it, _ in kept]
        kept = kept[nums.index(min(nums)):]

    if not kept:
        return [SectionSpan(section_name="Other", item="", start=0, end=n)]

    spans: list[SectionSpan] = []
    if kept[0][0] > 0:
        spans.append(SectionSpan(section_name="Other", item="", start=0, end=kept[0][0]))
    for i, (pos, item, title) in enumerate(kept):
        end = kept[i + 1][0] if i + 1 < len(kept) else n
        spans.append(SectionSpan(section_name=title or item, item=item, start=pos, end=end))
    return spans


def run_sections(doc_id: str, *, base=None) -> list[SectionSpan]:
    text = load_artifact("cleaned", doc_id, ext="txt", base=base)
    spans = detect_sections(text)
    persist_artifact("sections", doc_id, spans, base=base)
    return spans


def run_all(*, base=None) -> dict:
    ids = list_artifacts("cleaned", ext="txt", base=base)
    per = {i: run_sections(i, base=base) for i in ids}
    return {"files": len(per), "sections": per}


if __name__ == "__main__":
    r = run_all()
    if not r["sections"]:
        print("Stage 4 sections: no data/cleaned artifacts — run `python -m src.pipeline.clean` first.")
    else:
        counts = [len(v) for v in r["sections"].values()]
        detected = sum(1 for v in r["sections"].values() if not (len(v) == 1 and v[0].item == ""))
        print(f"Stage 4 sections: {r['files']} files; sections detected in {detected}/{r['files']}; "
              f"avg {sum(counts) / len(counts):.1f} spans/file (max {max(counts)}).")

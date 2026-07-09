# Skill: section-detection

**Purpose.** Stage 4. SEC filings are already structured into named items/sections; detect them
deterministically and persist their boundaries so chunking can split *within* sections. No LLM.

**When to invoke.** Work in `src/pipeline/sections.py`.

## Sections to detect
- **10-K:** Item 1 Business, 1A Risk Factors, 1C Cybersecurity, 3 Legal Proceedings, 7 MD&A,
  7A Market Risk, 8 Financial Statements.
- **10-Q:** Part I Financial Statements, MD&A, 3 Market Risk, 4 Controls; Part II 1 Legal Proceedings,
  1A Risk Factors.

## How to do it
1. Load `data/cleaned/<doc_id>.txt`. Scan for item/section headings with anchored regexes
   (`^\s*Item\s+\d+[A-Z]?\.`). Match on the human-readable heading, not the table of contents entry
   (the real section body is usually the *last* occurrence of the heading).
2. Record each section as `{section_name, start, end}` (character offsets into the cleaned text).
   `end` of one section = `start` of the next; last section runs to EOF.
3. Persist to `data/sections/<doc_id>.json`. Chunking reads this to know where each section's text is.
4. Handle missing sections gracefully (not every filing has every item) — record only what's found;
   text outside any detected section goes to a `"Preamble"`/`"Other"` bucket, not dropped.

## Bad example
```python
# BAD: splits on the first "Item 1A" (the TOC entry, not the section); loses offsets
idx = text.find("Item 1A")           # matches the table of contents, a few lines in
risk = text[idx: idx+5000]           # arbitrary window, wrong content, nothing persisted
```

## Good example
```python
import re
from src.observability import load_artifact, persist_artifact
HEAD = re.compile(r"^\s*(Item\s+\d+[A-Z]?)\.?\s+([A-Z][A-Za-z ,&']{3,60})", re.M)
NAMES = {"Item 1A": "Risk Factors", "Item 7": "MD&A", "Item 8": "Financial Statements", ...}

def run_sections(doc_id):
    text = load_artifact("cleaned", doc_id, ext="txt")
    hits = list(HEAD.finditer(text))
    # keep the LAST occurrence of each item (skip the TOC), then sort by position
    last = {m.group(1): m for m in hits}
    marks = sorted(last.values(), key=lambda m: m.start())
    sections = []
    for i, m in enumerate(marks):
        end = marks[i+1].start() if i+1 < len(marks) else len(text)
        sections.append({"section_name": NAMES.get(m.group(1), m.group(2).strip()),
                         "item": m.group(1), "start": m.start(), "end": end})
    persist_artifact("sections", doc_id, {"doc_id": doc_id, "sections": sections})
```

## Failure modes seen
- Matching the table-of-contents entry instead of the real section body.
- Assuming every filing has every item → crashes / empty sections; handle absence.
- Dropping text that falls outside detected headings → whole passages become unretrievable.
- Storing text copies instead of offsets → artifacts bloat and drift from `data/cleaned/`.

## MUST NOT
- MUST NOT use an LLM for section detection (deterministic only).
- MUST NOT drop text that isn't inside a recognized section — bucket it.
- MUST NOT skip persisting `data/sections/` — chunking depends on it and it must be inspectable.

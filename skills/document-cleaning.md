# Skill: document-cleaning

**Purpose.** Stage 2. Remove retrieval noise while preserving all business content, and persist the
cleaned text to `data/cleaned/`. This is where the XBRL blob is stripped. Deterministic — no LLM.

**When to invoke.** Work in `src/pipeline/clean.py`.

## Remove vs preserve
**Remove:** the leading XBRL/us-gaap tag blob, XML/XBRL namespace declarations, repeated technical
identifiers (CIK-date concatenations), repeated whitespace/blank runs, page-boundary artifacts,
formatting cruft.
**Preserve:** all business prose, section titles/headings, financial terminology, and **tables**
(keep rows aligned; do not flatten a table into a line of numbers).

## How to do it
1. Load `data/raw/<doc_id>.txt` (`observability`). Split off the header (already parsed) from the body.
2. **Strip the XBRL blob:** the body opens with a wall of `us-gaap:`/`srt:`/`<ticker>:` tags and
   CIK-date runs. Anchor on the first prose marker
   (`"UNITED STATES", "SECURITIES AND EXCHANGE COMMISSION", "FORM 10-"`) and keep from there.
2. Collapse repeated whitespace/newlines; drop obvious artifacts. Keep it conservative — when unsure,
   keep the text. Losing a risk factor is worse than leaving a stray newline.
3. Persist to `data/cleaned/<doc_id>.txt`. Because it's persisted, you can diff raw vs cleaned to
   confirm nothing important was removed (that's the point of observability).

## Bad example
```python
# BAD: aggressive regex that also eats business text and tables; nothing persisted
text = re.sub(r"[^a-zA-Z ]", "", raw)     # deletes numbers ($ figures!), table structure, punctuation
return text.lower()                        # destroys tickers, section titles, financial meaning
```

## Good example
```python
import re
from src.observability import load_artifact, persist_artifact
ANCHOR = re.compile(r"UNITED STATES\s*SECURITIES AND EXCHANGE COMMISSION|FORM 10-[KQ]", re.I)
XBRL_LINE = re.compile(r"^\s*\d{6,}(us-gaap|srt|dei|[a-z]{2,6}):", re.I)

def run_clean(doc_id):
    raw = load_artifact("raw", doc_id, ext="txt")
    body = raw.split("=" * 60, 1)[-1]
    m = ANCHOR.search(body); body = body[m.start():] if m else body   # drop leading XBRL blob
    body = "\n".join(l for l in body.splitlines() if not XBRL_LINE.match(l))  # residual tag lines
    body = re.sub(r"\n{3,}", "\n\n", body).strip()                    # collapse blank runs
    persist_artifact("cleaned", doc_id, body, ext="txt")             # inspectable
```

## Failure modes seen
- Over-aggressive cleaning that strips numbers, `$`, table alignment, or whole sections → answers
  lose the figures they need. **Inspect `data/cleaned/` to catch this.**
- Lower-casing / punctuation stripping that destroys tickers and financial terms.
- Leaving the XBRL blob in → tag soup pollutes retrieval and inflates cost.
- Cleaning in memory without persisting → can't tell whether cleaning removed too much.

## MUST NOT
- MUST NOT use an LLM to clean (deterministic only).
- MUST NOT remove business text, section titles, numbers/units, or table content.
- MUST NOT skip persisting `data/cleaned/` — the raw↔cleaned diff is the safety check.
- MUST NOT let the XBRL blob survive into `data/cleaned/`.

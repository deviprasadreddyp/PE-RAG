# Skill: document-ingestion

**Purpose.** Stage 1. Read every SEC filing from `edgar_corpus/`, validate it, read the metadata
header, and persist the raw, unmodified document to `data/raw/`. Cleaning is a **separate** stage
(`document-cleaning`) — ingestion does not modify content.

**When to invoke.** Work in `src/pipeline/ingest.py`.

## Corpus facts
- `edgar_corpus/` holds 246 `.txt` filings + `manifest.json`. `manifest.json` is a dict with
  `corpus`, `description`, `file_count`, `filing_types` (`{"10-K": 89, "10-Q": 157}`), and `files`
  (the authoritative filename list — iterate this, don't glob blindly).
- Filename: `TICKER_FORM_[PERIOD]_YYYY-MM-DD_full.txt`. `PERIOD` (e.g. `2024Q3`) is present on most
  but NOT all files.
- Each file: a **metadata header** (`Company:`, `Ticker:`, `Filing Type:`, `Filing Date:`,
  `Report Period:`, `Quarter:`, `CIK:`, `Source:`, `URL:`) then a `====` line, then the body (which
  opens with a large XBRL/us-gaap blob — that gets removed in the cleaning stage, not here).

## How to do it
1. Read the file list from `manifest.json`. Validate each file: exists, UTF-8 decodable, filename
   matches the expected pattern. Send failures to a dead-letter list with the reason — never drop
   silently.
2. Split on `====` into `header` and `body`. Keep both; do NOT strip the XBRL blob here (that's
   `document-cleaning`).
3. Persist the raw document to `data/raw/<doc_id>.txt` via `persist_artifact` (`observability`).
   `doc_id` = a stable id derived from the filename, e.g. `AAPL_10K_2024`.
4. Hand the header to `metadata-schema` for deterministic metadata extraction (a separate stage).

## Bad example
```python
# BAD: globs, cleans + chunks inline, persists nothing, derives metadata from filename only
for p in glob.glob("edgar_corpus/*.txt"):
    text = strip_everything(open(p).read())   # cleaning mixed into ingestion, nothing saved
    chunks = split(text)                        # no data/raw artifact to inspect later
```

## Good example
```python
import json, re
from src.observability import persist_artifact
PAT = re.compile(r"^(?P<ticker>[A-Z]+)_(?P<form>10[KQ])_.*\.txt$")

def run_ingest():
    manifest = json.load(open("edgar_corpus/manifest.json", encoding="utf-8"))
    dead = []
    for fname in manifest["files"]:
        if not PAT.match(fname): dead.append((fname, "bad filename")); continue
        try: raw = open(f"edgar_corpus/{fname}", encoding="utf-8").read()
        except UnicodeDecodeError: dead.append((fname, "encoding")); continue
        doc_id = fname.replace("_full.txt", "")
        persist_artifact("raw", doc_id, raw, ext="txt")   # inspectable, unmodified
    if dead: persist_artifact("raw", "_dead_letter", dead)
```

## Failure modes seen
- Globbing instead of using `manifest.json` (the authoritative list).
- Cleaning/chunking mixed into ingestion → no raw artifact, no separation of stages.
- Silently skipping a filing on error → data loss with no record.
- Deriving metadata from the filename here → drops period on odd filenames (see `metadata-schema`).

## MUST NOT
- MUST NOT modify content in this stage (no XBRL strip, no whitespace collapse) — persist raw as-is.
- MUST NOT skip persistence — `data/raw/` must contain every ingested filing.
- MUST NOT write into `edgar_corpus/` (read-only).
- MUST NOT drop a filing silently — dead-letter it with the reason.

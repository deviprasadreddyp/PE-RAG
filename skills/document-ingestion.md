# Skill: document-ingestion

**Purpose.** Load SEC filings from `edgar_corpus/`, read the metadata header, and strip the XBRL
noise blob before any chunking or embedding.

**When to invoke.** Any work in `sec_rag/ingest/loader.py` or `parser.py`; anything that reads the
corpus.

## Corpus facts
- `edgar_corpus/` holds 246 `.txt` filings + `manifest.json`. `manifest.json` is a dict with
  `corpus`, `description`, `file_count`, `filing_types` (`{"10-K": 89, "10-Q": 157}`), and `files`
  (a list of filenames). Use it as the authoritative file list — do not glob blindly.
- Filename: `TICKER_FORM_[PERIOD]_YYYY-MM-DD_full.txt` (e.g. `AAPL_10K_2022Q3_2022-10-28_full.txt`).
  `PERIOD` (e.g. `2024Q3`) is present on most but NOT all files (`AAPL_10K_2025-10-31_full.txt`).
- Each file: a **metadata header** (`Company:`, `Ticker:`, `Filing Type:`, `Filing Date:`,
  `Report Period:`, `Quarter:`, `CIK:`, `Source:`, `URL:`) then a line of `====`, then the body.
- **The body opens with a large XBRL / us-gaap tag blob** — a wall of
  `0000320193us-gaap:CommonStock...` machine data — before the human-readable filing that begins
  around `UNITED STATESSECURITIES AND EXCHANGE COMMISSION...` / `FORM 10-K`.

## How to do it
1. Read the file list from `manifest.json`. For each file, split on the `====` separator into
   `header` and `body`.
2. Parse the header line-by-line into a metadata dict (`skills/metadata-schema`). Trust the header
   over the filename; use the filename only to cross-check and to backfill a missing period.
3. **Strip the XBRL blob:** detect the leading run of concatenated `us-gaap:`/`srt:`/`<ticker>:` tags
   and CIK-date sequences and drop it. Anchor on the first real prose marker
   (`"UNITED STATES", "SECURITIES AND EXCHANGE COMMISSION", "FORM 10-"`) and keep from there.
4. Return `(metadata, clean_body)` for the chunker. Never pass raw body downstream.

## Bad example
```python
# BAD: globs the dir, embeds the whole file including the XBRL blob, ignores the header
for path in glob.glob("edgar_corpus/*.txt"):
    text = open(path).read()
    ticker = path.split("_")[0]          # loses period, cik, url; wrong for odd filenames
    chunks = split(text)                 # XBRL tag soup goes straight into the index
```

## Good example
```python
import json, re
SEP = "=" * 60
PROSE_ANCHOR = re.compile(r"UNITED STATES\s*SECURITIES AND EXCHANGE COMMISSION|FORM 10-[KQ]", re.I)

def load(path: str) -> tuple[dict, str]:
    raw = open(path, encoding="utf-8").read()
    header, _, body = raw.partition(SEP)
    meta = parse_header(header)                      # -> ticker, company, form, period, cik, url...
    m = PROSE_ANCHOR.search(body)
    clean = body[m.start():] if m else body          # drop the leading XBRL blob
    return meta, clean
```

## Failure modes seen (guard against these)
- Tool globs the corpus and ignores `manifest.json` → misses that file names are authoritative.
- Tool derives all metadata from the filename → drops `period` on filenames without it, and gets
  CIK/URL wrong. **Read the header.**
- Tool embeds the XBRL blob → retrieval returns tag soup, cost balloons, answers degrade.
- Tool assumes every file has a `Quarter:` line — some 10-Ks don't; handle missing fields.

## MUST NOT
- MUST NOT embed, index, or chunk the XBRL/us-gaap blob.
- MUST NOT trust the filename over the header for metadata.
- MUST NOT write into `edgar_corpus/` — it is read-only.
- MUST NOT drop a filing silently on a parse error — send it to a dead-letter list with the reason.

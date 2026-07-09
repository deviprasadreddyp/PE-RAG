# Skill: chunk-enrichment

**Purpose.** Stage 6. Before embedding, prepend a short context header (Company / Filing / Year /
Section) to each chunk's text. This measurably improves embedding quality and retrieval — the
embedding then "knows" whose filing, which form, which year, and which section the text is from.

**When to invoke.** Work in `src/pipeline/enrich.py` (between chunking and embedding).

## How to do it
1. Load `data/chunks/<doc_id>.json`. For each chunk, build a header from its metadata and prepend it
   to the text. Keep the header compact and consistent (the same shape for every chunk).
2. **Enrich the text that gets embedded; keep the original chunk text separately** for display and
   citation. Store both: `text` (original) and `embed_text` (enriched). Do NOT show the enrichment
   header to the user or let it pollute the answer.
3. The enriched `embed_text` is what `embedding-generation` embeds; the vector store keeps the
   original `text` for the context block.

## Enrichment header format
```
Company: Apple Inc | Filing: 10-K | Year: 2024 | Section: Risk Factors
---
<original chunk text>
```

## Bad example
```python
# BAD: mutates the chunk's display text (so the header leaks into answers/citations),
#      and the header format varies per chunk (weakens the signal)
c["text"] = f"apple 2024 stuff\n{c['text']}"     # now the UI shows this; citation text is polluted
```

## Good example
```python
from src.observability import load_artifact, persist_artifact

def enrich(chunk):
    hdr = (f"Company: {chunk['company']} | Filing: {chunk['form']} | "
           f"Year: {chunk['fiscal_period'] or chunk['filing_date'][:4]} | Section: {chunk['section']}")
    return {**chunk, "embed_text": f"{hdr}\n---\n{chunk['text']}"}   # original text untouched

def run_enrich(doc_id):
    chunks = load_artifact("chunks", doc_id)
    persist_artifact("chunks", doc_id, [enrich(c) for c in chunks])  # now carries embed_text
```

## Failure modes seen
- Enriching the display `text` in place → the header leaks into the answer and the citation snippet.
- Inconsistent header format across chunks → dilutes the signal it's meant to add.
- Enriching after embedding (no effect) or forgetting to embed `embed_text` (embeds raw text).
- Putting huge metadata dumps in the header → wastes tokens, drowns the actual content.

## MUST NOT
- MUST NOT overwrite the original chunk `text` — keep `text` (display/citation) and `embed_text` (embed) separate.
- MUST NOT show the enrichment header to the user.
- MUST NOT vary the header format between chunks.

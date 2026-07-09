# Chunking Strategy: Section-Aware Hierarchical Chunking with Recursive Boundary Preservation

SEC filings are **hierarchical business documents**, not plain text. Their sections
(Business, Risk Factors, MD&A, Financial Statements, Legal Proceedings, Cybersecurity, …)
already are semantically coherent business concepts. Our goal is **not to split the document**
but to **preserve this hierarchy while producing retrieval-sized chunks.**

`RecursiveCharacterTextSplitter` is not the strategy — it is the boundary-preserving *algorithm*
we use inside each section.

## The hierarchy

```
SEC Filing
├── Metadata (company, ticker, form, fiscal period, CIK, source URL)
├── Section 1  (parent)          ── Chunk 0, Chunk 1, Chunk 2
├── Section 2  (parent)          ── Chunk 0, Chunk 1
└── Section 3  (parent)          ── Chunk 0, Chunk 1, Chunk 2
```

Every chunk carries: company · filing type · fiscal year/quarter · **section title** ·
`section_index` (which parent) · `section_chunk_index` (position within the parent) ·
`chunk_index` (global order) · source document.

## Two stages

1. **Section detection (hierarchy creation)** — `src/pipeline/sections.py` (Stage 4). Detect the
   filing's natural item boundaries. Each section becomes a parent node with character offsets.
   Nothing is chunked yet; we have simply understood the structure. (92% of the corpus parses; the
   rest fall back to a single "Other" parent so nothing is lost.)

2. **Recursive chunking within each section** — `src/pipeline/chunk.py` (Stage 5). Split **only
   inside** each section, never across two. The splitter tries paragraph → sentence → whitespace →
   character in order, so it keeps "Revenue increased because…" together instead of cutting it into
   "Revenue increased" / "because…". A chunk is never `end-of-Business + start-of-Risk-Factors`.

## Enrichment (Stage 6)

Before embedding, each chunk is prefixed with its parent context so the embedding carries the
business concept, while the original `text` is preserved for display and citation:

```
Company: Apple | Filing: 10-K | Year: 2024 | Section: Risk Factors
---
<chunk text>
```

## Why not the alternatives

- **Fixed-size chunking** would produce chunks mixing unrelated concepts (company overview + risk
  discussion in one embedding) → worse retrieval.
- **Semantic chunking** adds another model, more preprocessing time, and complexity. The SEC filing
  *already tells us* where topics begin and end, so we leverage that structure instead of inferring it.
- **Parent–child retrieval** would work well and is the first upgrade we'd evaluate in production, but
  for a 246-filing, time-boxed MVP, section-aware hierarchical chunking keeps most of the benefit with
  far less machinery.

## Why it suits SEC filings

Analyst questions are about business concepts — Risk Factors, MD&A, Financial Statements,
Cybersecurity — not arbitrary spans. Preserving sections as semantic boundaries means each embedding
represents a coherent topic. The result is **semantically meaningful**, **embedding-friendly**,
**retrieval-efficient**, and **production-ready** (section metadata supports later filtering, ranking,
and analytics without changing the architecture).

# 01 - Product Spec: Full Rechunk + Full Index

## Problem
- **Business question:** Help a PE analyst answer company, trend, risk, legal, and financial questions over the full SEC corpus with grounded citations.
- **Who asks it:** PE analyst / CTO demo reviewer.
- **Trigger:** Current dense index only covers priority tickers, and chunk/metadata quality needs to be stable before full re-embedding.

## Query types in scope
- [x] Single-company lookup: "What was NVIDIA's FY2024 revenue?"
- [x] Cross-company comparison: "Compare Apple and Tesla risk factors."
- [x] Cross-period trend: "How has NVIDIA's growth outlook changed over two years?"
- [x] Sector / thematic: "What regulatory risks do major pharma companies face?"
- [x] Definitional / qualitative: "How does Costco describe its membership model?"

## Success criteria
- **Answer quality:** Final answers cite retrieved evidence and refuse unsupported questions.
- **Retrieval quality:** BM25 and dense coverage include every regenerated chunk.
- **Latency budget:** Retrieval remains deterministic and bounded by configured top-k/candidate pool.
- **Cost ceiling:** One embedding rebuild over stable chunks; query path still uses one final LLM call.
- **Refusal correctness:** Out-of-domain eval cases continue to refuse.

## Hidden requirements
- Citations must carry company/ticker, form, fiscal period/year, section, and source URL where present.
- Numeric fidelity must preserve figures, units, dates, and fiscal periods verbatim.
- User filters can reference ticker/company, form, year, quarter, and section intent.
- Corpus is static for this rebuild; later runs remain idempotent through stable chunk IDs and embedding cache.

## Edge cases
- XBRL tag soup before the filing body.
- Useful XBRL facts available only in header/cover text rather than clean XML.
- Financial tables with headers, units, rows, and footnotes.
- Ambiguous fiscal year vs filing year.
- Amended/restated filing indicators.

## Assumptions
- **Confirmed:** OpenAI API key is configured for `text-embedding-3-large`.
- **Confirmed:** Chroma/BM25 artifacts can be rebuilt from `data/chunks` and `data/embeddings`.
- **Confirmed:** No LLM is used for cleaning, metadata, sectioning, chunking, embedding, retrieval, or citations.

## Out of scope
- Live SEC download.
- XBRL numeric fact database.
- Additional answer-generation prompt changes.

## Open questions
- None blocking for the MVP rebuild.

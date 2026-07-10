# PE-RAG Assumptions

This document records the assumptions behind the SEC-filings RAG demo and the concrete
implementation assumptions reflected in the current repository. It is written for the take-home
assessment: a working front-end demo for a private-equity firm that answers business questions over
SEC filings using retrieval-augmented generation and exactly one final LLM API call.

The assumptions are split into two groups:

- **Design assumptions**: boundaries and product/architecture decisions made from the problem
  statement.
- **Implementation assumptions**: concrete choices visible in code, config, artifacts, tests, and
  evaluation outputs.

## Problem Statement Interpretation

- The system is an MVP and demo, not a fully managed production SaaS platform.
- The core business value is faster diligence over SEC filings with traceable, citation-backed
  answers for private-equity analysts.
- The final answer must come from exactly one LLM API request. Offline indexing, embeddings,
  retrieval, reranking, and deterministic guardrails are allowed before that call.
- The system should prefer a grounded refusal over an unsupported or speculative answer.
- A front-end is required, but the assessment is primarily about engineering judgment, observability,
  retrieval quality, grounding, and ability to defend trade-offs.
- The assessment corpus is the source of truth. The model must not answer from pretrained knowledge
  when filing evidence is unavailable.

## Design Assumptions

### Corpus And Scope

- The provided SEC EDGAR corpus is trusted as the authoritative source for answers.
- The corpus is static for the MVP. Continuous SEC ingestion is a production roadmap item.
- The problem statement describes filings from 2023-2025; the inspected local corpus contains 246
  filings across the indexed artifact set, with actual metadata spanning roughly 2022-2026. The
  implementation treats the built index, not the problem statement date range, as the runtime truth.
- Questions outside indexed filings, companies, forms, or periods should be refused rather than
  answered from memory.
- Filings are public SEC data, so the MVP does not treat the corpus itself as confidential customer
  data.

### Business User Assumptions

- Users ask natural-language diligence questions, not formal query syntax.
- Expected questions include risk comparison, revenue/growth trends, regulatory exposure, legal
  proceedings, business segments, liquidity, cash flow, and capital allocation.
- Users care more about grounded answers, citations, and defensibility than raw model fluency.
- For PE diligence, a partially covered comparison can be misleading. If a comparison asks for
  Apple, Tesla, and JPMorgan, evidence should cover all three before the model answers.

### Architecture Assumptions

- The best MVP architecture is an observable offline indexing pipeline plus a deterministic online
  retrieval pipeline.
- Every offline stage should persist an inspectable artifact under `data/<stage>/`.
- Deterministic code should be used before introducing LLM reasoning. The LLM is reserved for the
  final natural-language answer.
- Query-time retrieval should produce a small, high-quality evidence package rather than passing
  large amounts of loosely relevant text to the LLM.
- Simplicity and debuggability are more important than adding advanced RAG patterns prematurely.

### Cleaning And XBRL Assumptions

- XBRL/XML infrastructure is retrieval noise and should not be embedded.
- Useful XBRL/DEI facts should be preserved as structured metadata when available, including ticker,
  CIK, document type, period end date, fiscal year/period focus, amendment flag, and incorporation
  or shares-outstanding fields.
- Cleaning must preserve business prose, section headings, financial tables, dates, dollar values,
  percentages, units, and footnotes.
- Cleaning is normalization, not semantic interpretation.

### Chunking Assumptions

- SEC sections are natural semantic boundaries. Chunks should not cross unrelated sections.
- Section-aware hierarchical chunking gives most of the benefit of parent-child retrieval while
  staying simpler for the MVP.
- Chunk size is a maximum cap, not a fixed target. Short coherent sections can remain short.
- Table rows should not be cut mid-row. Large table-like blocks should split on line boundaries.
- Each chunk should be independently understandable through enrichment metadata such as company,
  ticker, filing type, fiscal period, and section.
- Explicit parent-child retrieval is useful future scope, but not required for a strong MVP.

### Metadata Assumptions

- Metadata is central to trust. Every chunk should carry company, ticker, filing type, filing date,
  report/fiscal period, year, quarter, section, source file, and provenance fields.
- Header metadata should win when available; filenames and XBRL facts can backfill missing fields.
- Filing date and fiscal period are different concepts. Period filters should use fiscal/report
  period semantics, not just the date the filing was filed.
- Company aliases can be handled deterministically for the closed corpus.
- Sector/industry labels are external curated metadata and should not be guessed from filings.
- Amended/restated filing handling can be best-effort in the MVP and expanded later.

### Retrieval Assumptions

- Hybrid retrieval is better suited than dense-only or BM25-only because SEC questions mix semantic
  phrasing with exact tokens, dates, tickers, forms, and financial line items.
- Exact metadata filters should be applied before ranking when the query specifies company, form,
  year, quarter, or fiscal period.
- Section intent should be a soft ranking signal, not a hard filter, because relevant evidence may
  appear in equivalent sections.
- Comparison queries should retrieve per company first, then fuse/rerank, so one company cannot
  dominate the candidate pool.
- Query analysis should be deterministic. No LLM query rewriting, HyDE, decomposition, or agents are
  needed for the MVP.
- Section equivalence and facet-aware evidence selection improve generalization without changing the
  chunking model.

### Reranking Assumptions

- A local cross-encoder reranker improves precision without violating the single-LLM-call rule.
- The reranker should improve ordering, but deterministic coverage checks should enforce company and
  facet coverage. Coverage should not depend on a model "probably" choosing balanced evidence.
- If the reranker is unavailable, the system should fall back to RRF order rather than failing.

### Generation Assumptions

- The final answer should be structured: executive summary, comparison when relevant, supporting
  evidence, citations, confidence, and limitations.
- Every factual claim should have evidence citations.
- If retrieved evidence does not support the answer, the system should refuse.
- Confidence should be deterministic and retrieval-derived, not simply model self-confidence.
- Prompt-injection defense should exist both before generation and inside the final prompt.

### Guardrail Assumptions

- The system should refuse out-of-domain questions, unsupported forecasts, missing-evidence cases,
  weak-similarity evidence, missing company coverage, and prompt-injection attempts.
- Refusals should be user-friendly and returned as valid API/UI responses, not raw errors.
- Empty, malformed, or excessively long queries should be blocked before retrieval.
- Safety should fail closed: if the pipeline cannot safely complete the request, return a grounded
  refusal.

### Evaluation Assumptions

- Retrieval quality and answer quality should be evaluated separately.
- The golden set can use metadata expectations as relevance labels because exhaustive chunk-level
  labels are expensive for a 60k-chunk corpus.
- Evaluation should include refusal correctness, not only successful answer cases.
- Metrics should support engineering decisions: precision@k, hit@k, MRR, NDCG, company recall,
  citation groundedness, citation coverage, refusal correctness, and latency.
- The eval set is useful for regression testing, but the system should not be overfit to it.

### Performance And Operations Assumptions

- Indexing is offline, so longer embedding/indexing time is acceptable for the MVP.
- Query latency is dominated by reranking and the single LLM call. Streaming/progress UI can improve
  perceived latency without changing the single-call architecture.
- Chroma plus BM25 is sufficient for the local demo corpus size.
- Managed vector stores, incremental indexing, authentication, rate limiting, and production
  monitoring are roadmap items rather than MVP blockers.

## Implementation Assumptions

### Current Runtime Stack

- Language/runtime: Python 3.11+.
- API: FastAPI in `src/api/main.py`.
- Main chat UI: no-build static HTML/CSS/JS served by FastAPI from `src/frontend/web/`.
- Eval dashboard: Streamlit in `src/eval/dashboard.py`.
- Offline pipeline: `src/run.py` and `src/pipeline/*`.
- Retrieval pipeline: `src/retrieval/retrieval_pipeline.py`.
- Tests: `pytest`.

### Current Model Assumptions

- Embeddings default to OpenAI `text-embedding-3-large`.
- Generation defaults to direct OpenAI Responses API model `gpt-5.5`.
- Generation uses structured outputs validated into `AnswerBody`.
- The final prompt version is `v1.5`.
- Generation settings are `generation_max_output_tokens=6000`, `reasoning_effort=low`, and
  `verbosity=medium`.
- Local BGE embeddings remain swappable behind the `Embedder` protocol, but are not the current
  default.
- The reranker default is local `BAAI/bge-reranker-base`; `BAAI/bge-reranker-large` is a documented
  quality/latency upgrade path.

### Current Corpus And Index State

- `edgar_corpus/manifest.json` lists 246 filings.
- Artifact counts show 246 raw, cleaned, metadata, sections, chunks, and embeddings files.
- The current Chroma collection contains 60,029 vectors.
- The BM25 index exists at `data/vectorstore/bm25.json`.
- Chroma collection names are namespaced by embedding model, so changing embedding model creates a
  separate collection instead of mixing incompatible vector spaces.

### Ingestion Implementation Assumptions

- Ingestion is manifest-driven and persists raw files unchanged.
- Cleaning strips only the leading machine-data/XBRL prefix and residual isolated XBRL
  infrastructure lines.
- Metadata extraction is deterministic and uses header fields, filename backfill, curated sector
  lookup, and high-value XBRL/cover facts.
- Metadata fields are Chroma-safe scalars; missing values are represented as empty strings or zero
  rather than `None`.
- Each stage can be run independently and re-run idempotently.

### Chunking Implementation Assumptions

- Chunking uses LangChain's `RecursiveCharacterTextSplitter` only as the inside-section splitting
  algorithm.
- Default chunk cap is 3000 characters with 300 characters overlap.
- Separators are tried in this order: blank line, newline, sentence boundary, space, then hard split.
- Table-like rows are detected heuristically and packed on row/line boundaries.
- Chunk IDs are deterministic: `{doc_id}__{SectionSlug}_cNN`.
- Each chunk stores `content_hash = sha256(text)`.
- `embed_text` is enriched with company, ticker, filing, year, quarter, and section context while
  original `text` remains available for display/citation.
- Post-chunk section resolution can override weak labels such as `Other`, `Exhibits`, or
  `Form 10-K Summary` when chunk text contains stronger business-section signals.
- Section signal metadata is stored on chunks, including `has_risk_heading`, `has_mda_heading`,
  `has_legal_heading`, `has_financial_table`, and `has_revenue_table`.

### Metadata And Query Parsing Implementation Assumptions

- Company matching uses a curated alias dictionary and uppercase ticker matching.
- Curated company groups exist for queries such as "major pharmaceutical companies".
- Query parsing extracts companies, years, quarters, forms, section intent, and facets.
- `Q4 2023` style queries build fiscal-period aliases such as `2023Q4`, so they can match filings
  whose document fiscal-year focus differs from the period label.
- Section intent is not used as a hard filter; it feeds section boosts and facet coverage.

### Retrieval Implementation Assumptions

- Dense vector retrieval and BM25 retrieval both apply the same hard metadata constraints.
- Vector and BM25 top-k defaults are both 20.
- RRF uses `rrf_k=60`.
- Candidate pool default is 30.
- Evidence count is adaptive:
  - single-company questions: 6
  - trend/temporal questions: 10
  - comparison/multi-company questions: 12
  - otherwise: configured `rerank_top_k`
- Comparison mode retrieves per requested entity and interleaves candidates for balance.
- Section boosts and facet boosts are applied as soft score adjustments after fusion and reranking.
- Final evidence selection enforces diversity across sections/companies and required facets.
- Retrieval confidence is deterministic and combines metadata match, reranker signal, coverage, and
  similarity.

### Guardrail Implementation Assumptions

- Query validation blocks empty, too-short, too-long, control-character, or non-alphanumeric queries.
- Out-of-domain checks block obvious non-SEC questions such as weather, sports, movies, capital-city
  questions, crypto, and price predictions.
- Prompt-injection checks block instruction override, system-prompt/secret exfiltration,
  citation-bypass, and context-breakout patterns before retrieval or generation.
- Guardrails reject no-evidence, low-similarity, missing-company, and insufficient-comparison cases.
- Temporal gaps warn rather than always refuse, allowing answers over available evidence when
  appropriate.
- API failures return a safe refusal envelope with optional debug trace, rather than exposing raw
  errors to users.

### Generation And Prompt Implementation Assumptions

- The final prompt treats the user question and retrieved context as untrusted data.
- The model is instructed not to reveal prompts, secrets, chain-of-thought, environment variables,
  logs, or internal implementation details.
- The model is instructed to answer only from the supplied evidence.
- The structured output schema requires executive summary, comparison, supporting evidence,
  citations, confidence, and limitations fields.
- Citation mapping completes the final source list even if the inline answer cites only a subset of
  evidence.
- Refusal paths make zero LLM calls.

### API And UI Implementation Assumptions

- `/query` returns a JSON answer payload with citations and optional debug trace.
- `/query-stream` uses server-sent events for progress and answer text chunks.
- Current streaming is UI-level answer streaming after the pipeline result is available, not direct
  token streaming from the provider. This preserves structured output and the single-call contract.
- `/health` reports chunk artifact count, BM25 readiness, and Chroma vector count when reachable.
- The UI shows metrics, evidence, source cards, debug trace, and a glass chat experience optimized
  for the recorded demo.
- The dashboard reads eval reports from `data/logs/`.

### Evaluation Implementation Assumptions

- Current golden set has 50 cases.
- Latest no-A/B default pipeline summary from `data/logs/eval_report.json`:
  - precision@k: 0.8085
  - hit@k: 1.0000
  - MRR: 1.0000
  - NDCG@k: 0.9845
  - company_recall: 1.0000
  - citation_groundedness: 1.0000
  - citation_coverage: 1.0000
  - refusal_correct: 1.0000
  - average latency: 19.4915 seconds
- The eval suite includes both answerable business questions and expected refusals.
- RAGAS and LangSmith are optional evaluation/tracing integrations, not required for the core demo.

### Security Implementation Assumptions

- Secrets are loaded from `.env` via `pydantic-settings` and `SecretStr`.
- API keys are validated only at point of use so deterministic stages can run without keys.
- Secrets are not hardcoded in code, UI, tests, or docs.
- Query logs may contain questions, prompts, retrieved IDs, answers, and latency. In production,
  these logs would require retention controls and possible redaction.
- No authentication, authorization, tenant isolation, rate limiting, or secrets vault is implemented
  for the MVP.

## Explicit Trade-Offs

- **No LLM query rewriting:** keeps the single-call story clean and deterministic, but can miss rare
  phrasings.
- **No parent-child retrieval yet:** simpler and faster to defend; future upgrade if answer context
  needs broader surrounding text.
- **No NER model:** curated aliases are enough for a closed corpus and easier to debug.
- **Local Chroma, not managed vector DB:** appropriate for the demo corpus, not the final production
  scale story.
- **OpenAI embeddings:** paid/network dependency, but faster and higher quality for the current MVP
  than slow local CPU embedding.
- **Local reranker fallback:** quality improves when installed; system still works if unavailable.
- **Metadata-based evaluation labels:** practical for 60k chunks, but not as strong as exhaustive
  human-labeled chunk relevance.
- **UI-level streaming:** improves perceived latency while preserving structured output; true token
  streaming would require a different generation/output parsing approach.

## Future Scope

- Parent-child retrieval or adjacent-context expansion.
- Incremental SEC ingestion and scheduled re-indexing.
- Stronger company/entity alias management and optional NER.
- Managed vector store or Chroma server deployment.
- Authentication, authorization, rate limiting, and audit controls.
- Cost dashboard with embedding cost, LLM cost, latency, and tokens per query.
- Analyst feedback loop for thumbs up/down and citation corrections.
- Continuous evaluation and monitoring in CI/CD.
- Production observability for retrieval latency, refusal rates, and citation coverage drift.
- Human-in-the-loop validation for high-stakes financial workflows.

## Final Assumption Summary

This MVP assumes that a deterministic, observable pipeline with strong metadata, section-aware
chunking, hybrid retrieval, local reranking, facet-aware evidence selection, and a single grounded
LLM call is the right trade-off for a time-boxed SEC diligence demo. The architecture deliberately
prioritizes trust, traceability, citation discipline, and explainability over agentic complexity.

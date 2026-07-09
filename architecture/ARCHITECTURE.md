# Architecture — Business · Logical · Physical

PE-RAG is specified at three levels so every decision is explicit and defensible.

| Level | Question it answers | Where |
|---|---|---|
| **Business** | *Why* does each component exist? What problem does it solve? | this file (below) |
| **Logical** | *What* is the pipeline, data flow, and each module's responsibility? | [`HLD.md`](HLD.md) + [`CHUNKING_STRATEGY.md`](CHUNKING_STRATEGY.md) |
| **Physical** | *How* exactly — classes, config, schema, algorithms, policies, logging? | [`PHYSICAL_SPEC.md`](PHYSICAL_SPEC.md) |

Supporting: [`ASSUMPTIONS.md`](ASSUMPTIONS.md) · [`corpus_notes.md`](corpus_notes.md) (dataset findings)
· [`DESIGN_AUDIT.md`](DESIGN_AUDIT.md) (design vs implementation status).

---

## Business Architecture — why each component exists

**The business problem.** A private-equity analyst needs to ask natural-language questions across
SEC filings and get answers they can *trust and act on* — grounded in the source documents, with
citations, at controlled cost. Wrong or unsourced financial figures are worse than "I don't know."

| Component | Business value it delivers |
|---|---|
| **Observable pipeline** (artifact per stage) | Trust & auditability — you can prove where every answer's evidence came from, and debug quality issues by inspecting any stage. |
| **Controlled/normalized cleaning** | Preserves the numbers, tables, and structure analysts actually ask about; avoids silently deleting business content. |
| **Deterministic metadata + hard filters** | An analyst asking about "Apple FY2024" never gets another company/period — correctness by construction, not luck. |
| **Section-aware chunking** | Each retrieved passage is one coherent business concept (Risk Factors, MD&A, …), matching how analysts think and improving answer relevance. |
| **Hybrid retrieval (BM25 + vector + RRF)** | Catches both exact financial vocabulary (tickers, line items) and semantic matches — higher recall on real questions. |
| **Single grounded LLM call** | Predictable latency and cost per question; the whole answer is traceable to one auditable request. |
| **Cite-or-refuse** | Regulatory-grade trust: the system declines rather than fabricating when the filings don't cover a question. |
| **Debug mode + evaluation** | Lets the team measure and defend retrieval/answer quality, and troubleshoot fast — the difference between a demo and an engineered system. |
| **Config-driven, deterministic, idempotent** | Reproducible, cheap to re-run and extend (incremental indexing), and easy to operate. |

**Why this design over alternatives:** we leverage the *structure the SEC filing already provides*
(sections, headers) instead of inferring it with extra models; we keep everything deterministic
except the one generation call, so the system is reproducible, cheap, and auditable — and any
quality issue is localizable to a specific, inspectable stage.

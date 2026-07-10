# Architecture Decision Records

Short, dated rationale for every significant technical choice. Format per record:
**Context → Decision → Consequences → Status.** Superseded records are kept, not deleted.

Status legend: ✅ Accepted · 🔁 Superseded · 🟡 Proposed.

---

## ADR-001 — Chroma as the vector store ✅
**Context.** MVP over ~32K chunks; need a persistent, embeddable, local vector DB with metadata
filtering and no server to operate.
**Decision.** Use **Chroma** (`PersistentClient`, cosine) via `langchain-chroma`, one collection.
**Consequences.** Zero-ops local persistence; native `where` metadata filters (our hard filters);
easy to swap later (behind our `VectorStore` protocol). Not built for massive scale — acceptable for
the corpus size; production path is a Chroma server or managed store (roadmap).

## ADR-002 — Hybrid retrieval (BM25 + vector) ✅
**Context.** Financial questions mix exact vocabulary (tickers, line items, "10-K", "FY2024") with
semantic phrasing ("how did margins trend"). Pure vector misses exact tokens; pure lexical misses
paraphrase.
**Decision.** Run **BM25 (lexical) and vector (semantic) independently**, then fuse.
**Consequences.** Higher recall on real queries; two indexes to maintain; fusion step required (ADR-003).

## ADR-003 — Reciprocal Rank Fusion, k=60 ✅
**Context.** BM25 scores and cosine similarities are on incomparable scales; averaging them needs
fragile normalization.
**Decision.** Fuse by **RRF**: `score(d) = Σ_r 1/(k + rank_r(d))`, `k=60`, ranks only.
**Consequences.** No score normalization; robust to outliers; industry-standard default. Implemented
ourselves (not via LangChain EnsembleRetriever) so the formula is explicit and testable.

## ADR-004 — OpenAI `text-embedding-3-large` for embeddings 🔁 (superseded by ADR-013)
**Context.** Need strong retrieval embeddings for dense financial prose and tables.
**Decision.** **OpenAI `text-embedding-3-large`**, batched + content-hash cached, behind an
`Embedder` protocol.
**Consequences.** High-quality dense retrieval; a paid dependency and a network call at query time.
**Superseded:** replaced by a local model (ADR-013) to drop the paid API and network hop for
embeddings; the `Embedder` protocol made this a drop-in swap.

## ADR-005 — Claude Opus 4.8 for the single generation call 🔁 (superseded by ADR-014)
**Context.** The one generative step must produce grounded, citation-bearing financial answers.
**Decision.** **Claude `claude-opus-4-8`** via `langchain_anthropic.ChatAnthropic` with structured output.
**Consequences.** Strong grounded reasoning, one auditable request.
**Superseded:** the generation provider was switched to OpenAI models via OpenRouter (ADR-014) at the
project owner's direction; the single-call constraint (ADR-008) and structured output are unchanged.

## ADR-006 — Section-aware hierarchical chunking, char max-cap ✅
**Context.** Filings are hierarchical (Items), have ~no blank-line paragraphs, and carry load-bearing
tables/figures.
**Decision.** Sections are the semantic parent; within each, a recursive splitter packs
boundary-preserving pieces **up to a max cap** (`chunk_max_chars=3000`, char-based, not token-based,
not fixed).
**Consequences.** Each chunk is one coherent concept; short sections stay whole; ~98% of chunks land
below the cap. Char-based avoids a tokenizer dependency; tunable by eval. (See `CHUNKING_STRATEGY.md`.)

## ADR-007 — Deterministic query understanding (no LLM before the answer) ✅
**Context.** Company/period/form/intent extraction must be reliable, explainable, and fast; the
assignment prizes a single LLM call.
**Decision.** **Rule-based** classification + regex + a company dictionary + a temporal parser — no
LLM for query understanding.
**Consequences.** Low latency, fully explainable/testable, zero extra generative calls. Edge phrasings
may be missed vs an LLM parser — accepted trade-off; the corpus's entities are a closed, known set.

## ADR-008 — Exactly one LLM call per request ✅
**Context.** Hard assignment constraint and a production discipline (cost/latency/auditability).
**Decision.** All retrieval/guardrails/formatting are deterministic; **one** `messages.create()`
produces the answer; refusals happen **before** the call (zero calls).
**Consequences.** Predictable cost/latency; no agentic loops, HyDE, rewriting, or decomposition.
Retrieval quality must carry the system — hence hybrid + rerank.

## ADR-009 — Local cross-encoder reranking ✅
**Context.** Bi-encoder recall is high but imprecise; we want precision without a second LLM call.
**Decision.** **Local cross-encoder** (`BAAI/bge-reranker-base`, `-large` optional) scores
(query, chunk) pairs; runs locally, no API. Behind a `Reranker` protocol with a deterministic fallback
when the model isn't installed.
**Consequences.** Higher precision on the top-k that reaches the prompt; adds a heavy optional
dependency (`sentence-transformers`/torch) — hence the skip-on-failure fallback (real run deferred,
like the embed/store runs).

## ADR-010 — Determinism, content hashing & embedding versioning ✅
**Context.** Re-runs must be reproducible; a model change must not silently mix incompatible vectors.
**Decision.** Deterministic section-aware chunk IDs; `content_hash = sha256(text)` per chunk;
`raw_index.json` sha256 for incremental indexing; **collection namespaced by embedding model**
(`sec_filings__<model>`); no timestamps/random values in artifacts.
**Consequences.** Byte-identical re-runs; content-addressed dedup/change detection; a model change ⇒ a
fresh index (no dimension/space mismatch). This is our embedding-versioning story.

## ADR-011 — LangChain as infrastructure only ✅
**Context.** LangChain accelerates I/O plumbing but its Chains/Agents hide control flow we must defend.
**Decision.** Use LangChain for Chroma, `Document`, `PromptTemplate`, output parsing, and
`ChatOpenAI` (pointed at OpenRouter) for the single call. **No Chains, no Agents, no memory** —
business logic (query understanding, planning, RRF, guardrails, evidence, citations) is our own
deterministic code. (Embeddings + reranker are local `sentence-transformers`, outside LangChain.)
**Consequences.** We keep full control and testability of every decision while still reusing battle-
tested connectors.

## ADR-012 — Observable artifact pipeline ✅
**Context.** Financial answers need auditability; quality bugs must be localizable.
**Decision.** Every offline stage persists an inspectable artifact to `data/<stage>/`; per-stage error
isolation dead-letters bad docs; a query log captures the full retrieval trace at request time.
**Consequences.** Any answer is traceable to its evidence and every stage is independently inspectable;
slightly more disk I/O — a worthwhile trade for trust and debuggability.

## ADR-013 — OpenAI `text-embedding-3-large` embeddings ✅ (reinstates ADR-004)
**Context.** For the priority MVP, OpenAI embeddings avoid slow local CPU/GPU setup while keeping
strong retrieval quality. The API cost for the priority SEC subset is small enough to be acceptable.
**Decision.** **OpenAI `text-embedding-3-large`** is the default embedding model, behind the existing
`Embedder` protocol. Content-hash cache unchanged; model-namespaced collection (ADR-010) rolls to a
fresh index automatically. `text-embedding-3-small` and local BGE remain one-setting alternatives.
**Consequences.** Requires `OPENAI_API_KEY` and network access during embedding/query-vector
generation. Indexing is faster and more reproducible across machines than local BGE on CPU. The
dimension/cost can be reduced by switching to `text-embedding-3-small` if needed.

## ADR-014 — OpenAI models via OpenRouter for generation ✅ (supersedes ADR-005)
**Context.** The project owner wants ChatGPT-family generation and a single provider key that can
reach many models.
**Decision.** The one grounded call uses **`openai/gpt-4o` via OpenRouter** — LangChain `ChatOpenAI`
pointed at OpenRouter's OpenAI-compatible `base_url`, with `.with_structured_output(AnswerBody)`.
`OPENROUTER_API_KEY` is used for generation; `OPENAI_API_KEY` is used for embeddings.
**Consequences.** One API request, structured output, provider-swappable by changing
`generation_model` (any OpenRouter model id) — no code change. Also removes the latent
`langchain-anthropic` dependency (never in requirements); `langchain-openai` is. Single-call
constraint (ADR-008) preserved.

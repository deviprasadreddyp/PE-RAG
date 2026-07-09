# The-RAG Harness — Design Doc

## What this harness is

A **harness** is the reusable context that makes a coding tool (Claude Code / Cursor) build
The-RAG *the way we want*, not the way the model's training-data average would. Instead of
re-explaining our architecture, conventions, and the single-LLM-call constraint every time we
start a feature, we encode all of it once — in `agents.md`, `templates/`, `skills/`, and `evals/` —
and point the tool at it.

This harness is built for one goal: **making it fast and predictable to extend, debug, and modify
The-RAG** — a RAG system that answers business questions over SEC filings in a single Claude call.
It is deliberately over-constrained. Predictability is the feature.

## The four components

| Component | Role |
|---|---|
| **`agents.md`** | The master file. Architecture, stack, folder layout, the skill glossary, and the non-negotiable rules. Loaded at the start of every session. |
| **`templates/`** | The development sequence. Product spec → technical spec → implementation plan. Every feature is built by filling these out, in order, then telling the tool to build the plan. |
| **`skills/`** | One opinionated how-to per capability (ingestion, chunking, retrieval, the single call, …). Each has a bad example, a good example, failure modes we've hit, and an explicit MUST-NOT list. |
| **`evals/`** | Proof it works. Rebuild an existing feature from scratch with only the harness loaded; compare to the hand-built version. If it diverges, a skill is missing or dull. |

## How to use it

1. **Start a fresh chat.** Do not carry a 50-message thread. `agents.md` is the context, not history.
2. **Load `agents.md`.** (`claude` reads it automatically at repo root; in Cursor, @-mention it.)
3. **State the feature** as a one-paragraph request, e.g. *"Add cross-company revenue-trend
   comparison to the retriever."*
4. The tool should then, on its own:
   - create `features/active/<name>/`,
   - instantiate and fill the three templates by reading the relevant skills,
   - build the implementation plan phase by phase, following the conventions,
   - log any prompt change in `prompts/CHANGELOG.md`.
5. **You should not have to babysit it or answer ten clarifying questions.** If you do, the harness
   needs a sharper skill or rule — fix that, don't just fix the code.

## What "good" looks like

Load the harness in a fresh chat and say *"Build a feature that adds sector-level regulatory-risk
comparison."* If the tool creates the feature folder, fills the three templates from the skills,
builds the feature with the right conventions (metadata filtering, single call, cite-or-refuse), and
needs ~zero back-and-forth — the harness is good. If it invents its own chunking, skips the metadata
filter, makes two LLM calls, or asks what vector store to use — the harness needs work.

## How the two skill systems relate

- **`skills/` (this harness):** project-specific, opinionated build instructions for The-RAG.
  Tool-agnostic (works in Cursor or Claude Code). This is what `agents.md` points to.
- **`.claude/skills/` (Claude Code only):** a general staff-engineer workflow library
  (requirements → design → review → test). Complementary; it shapes *how* Claude Code works, while
  `skills/` shapes *what* it builds here. Either can be used alone.

## Design decisions (and why)

- **Single Claude call is a first-class constraint, not an afterthought.** It shapes the whole
  design: everything expensive (embedding, retrieval, reranking, query parsing) happens *before* the
  one call. `skills/single-call-rag.md` and non-negotiable rule #1 enforce it.
- **Metadata filtering is the highest-leverage retrieval lever** for this corpus — most questions
  are scoped by company + period. So it's a mandatory architectural stage, not an option.
- **XBRL stripping and table-preservation are load-bearing.** The raw filings open with a machine-
  data blob and contain the financial tables that hold the answers; getting parsing right at the
  source matters more than any downstream cleverness. Hence dedicated skills and a non-negotiable rule.
- **Cite-or-refuse over confident-guess.** This is a finance/PE use case; a wrong number is worse
  than "I don't know." Grounding is enforced in the prompt and in `answer-grounding.md`.
- **Opinionated stack (Chroma + Voyage + Streamlit + Claude).** Chosen for a 4-hour build with good
  metadata filtering, finance-tuned embeddings, a fast demo UI, and the single-call generation model.
  Swappable behind protocols, but pinned so the tool doesn't re-litigate the choice every feature.

## Deliverables map (assessment ↔ repo)

| Assessment deliverable | Where it lives |
|---|---|
| README with setup/run | `README.md` (generated per `skills/frontend-streamlit` + build plan) |
| Indexing & retrieval code | `sec_rag/ingest/`, `sec_rag/index/`, `sec_rag/retrieval/`, `scripts/build_index.py` |
| Prompt iteration log | `prompts/CHANGELOG.md` |
| Final prompt template | `sec_rag/generation/prompt.py` |
| Front-end | `app.py` (Streamlit) |
| Example request | `evals/case-01-.../prompt.md` (and README quick-start) |
| Quality evaluation notes | `evals/` + `sec_rag/eval/` |

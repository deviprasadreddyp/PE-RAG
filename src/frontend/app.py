"""Streamlit UI for the PE-RAG SEC filings workbench.

The page shows the answer, sources, feedback, and an optional developer trace over
the deterministic pipeline. The final answer still comes from exactly one
structured LLM call; the UI uses progress updates and a typewriter reveal to
reduce perceived latency.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

from src.retrieval import feedback
from src.retrieval.retrieval_pipeline import run_query
from src.schemas import Citation

_THEME_CSS = """
<style>
:root {
  --rose-25: #fff8fb;
  --rose-50: #fff1f6;
  --rose-100: #ffe3ee;
  --rose-200: #ffc7dc;
  --rose-500: #d9467c;
  --rose-700: #9f234f;
  --ink: #211923;
  --muted: #706672;
  --line: #ead7df;
}

.stApp {
  background:
    radial-gradient(circle at 18% 6%, rgba(255, 199, 220, 0.44), transparent 30%),
    linear-gradient(135deg, #fff8fb 0%, #fff1f6 44%, #f8fbff 100%);
  color: var(--ink);
}

[data-testid="stHeader"] {
  background: rgba(255, 248, 251, 0.78);
  backdrop-filter: blur(14px);
  border-bottom: 1px solid rgba(234, 215, 223, 0.65);
}

[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #fff1f6 0%, #ffffff 100%);
  border-right: 1px solid var(--line);
}

[data-testid="block-container"] {
  padding-top: 2rem;
  max-width: 1220px;
}

.app-hero {
  border: 1px solid rgba(234, 215, 223, 0.9);
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(255,255,255,0.94), rgba(255,241,246,0.88));
  box-shadow: 0 18px 50px rgba(159, 35, 79, 0.10);
  padding: 1.25rem 1.35rem;
  margin-bottom: 1rem;
}

.eyebrow {
  color: var(--rose-700);
  font-size: 0.78rem;
  font-weight: 750;
  letter-spacing: 0;
  text-transform: uppercase;
  margin-bottom: 0.25rem;
}

.hero-title {
  color: var(--ink);
  font-size: 2.15rem;
  line-height: 1.1;
  font-weight: 780;
  margin: 0;
}

.hero-copy {
  color: var(--muted);
  font-size: 1rem;
  margin-top: 0.45rem;
  max-width: 760px;
}

.metric-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.75rem;
  margin: 0.85rem 0 1rem;
}

.mini-metric {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: rgba(255,255,255,0.82);
  padding: 0.75rem 0.85rem;
}

.mini-metric span {
  display: block;
  color: var(--muted);
  font-size: 0.78rem;
}

.mini-metric strong {
  display: block;
  color: var(--ink);
  font-size: 1.22rem;
  margin-top: 0.1rem;
}

.progress-card {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: rgba(255,255,255,0.9);
  padding: 0.85rem 1rem;
  color: var(--ink);
  box-shadow: 0 10px 26px rgba(159, 35, 79, 0.08);
}

.answer-label, .source-label, .debug-label {
  color: var(--rose-700);
  font-size: 0.82rem;
  font-weight: 760;
  text-transform: uppercase;
  letter-spacing: 0;
  margin: 1rem 0 0.35rem;
}

.stButton > button {
  border-radius: 10px;
  border: 1px solid var(--rose-200);
  background: linear-gradient(135deg, #d9467c, #9f234f);
  color: #ffffff;
  font-weight: 720;
  min-height: 2.6rem;
  box-shadow: 0 10px 22px rgba(217, 70, 124, 0.22);
}

.stButton > button:hover {
  border-color: var(--rose-700);
  color: #ffffff;
  transform: translateY(-1px);
}

.stTextArea textarea, .stTextInput input {
  border-radius: 12px;
  border-color: var(--line);
  background: rgba(255,255,255,0.95);
}

[data-testid="stMetric"] {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: rgba(255,255,255,0.82);
  padding: 0.8rem;
}

[data-testid="stExpander"] {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: rgba(255,255,255,0.76);
}

div[data-testid="stMarkdownContainer"] h2 {
  color: var(--ink);
  font-size: 1.18rem;
  border-bottom: 1px solid var(--line);
  padding-bottom: 0.25rem;
}

div[data-testid="stMarkdownContainer"] table {
  border: 1px solid var(--line);
  border-radius: 10px;
  overflow: hidden;
}

div[data-testid="stMarkdownContainer"] th {
  background: #fff1f6;
  color: var(--ink);
}

@media (max-width: 900px) {
  .metric-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .hero-title { font-size: 1.75rem; }
}
</style>
"""

_PROGRESS_MESSAGES = [
    "Parsing the question",
    "Applying metadata filters",
    "Running hybrid retrieval",
    "Reranking evidence",
    "Assembling cited context",
    "Generating the grounded answer",
    "Resolving citations",
]

_SAMPLE_QUERIES = [
    "Compare Apple, Tesla, and JPMorgan risk factors",
    "How has NVIDIA's revenue and growth outlook changed?",
    "What regulatory risks do UnitedHealth and Johnson & Johnson disclose?",
]

_TRACE_ORDER: list[tuple[str, str]] = [
    ("1. Query (validated)", "query"),
    ("2. Intents", "intents"),
    ("3. Companies / years", "companies"),
    ("4. Hard filter", "filter"),
    ("5. Retrieval plan", "plan"),
    ("5. Facets", "facets"),
    ("5. Section boosts", "section_boosts"),
    ("5. Facet targets", "facet_targets"),
    ("5. Expanded retrieval query", "expanded_query"),
    ("5. Balanced entities", "balanced_entities"),
    ("5. Scope guardrail", "scope_guardrail"),
    ("6. Vector candidate ids", "vector_ids"),
    ("6. BM25 candidate ids", "bm25_ids"),
    ("7. RRF-fused ids", "rrf_ids"),
    ("8. Reranked ids", "reranked_ids"),
    ("8. Section-prioritized ids", "section_prioritized_ids"),
    ("9. Adaptive evidence limit", "evidence_limit"),
    ("9. Diversified candidate ids", "diversified_ids"),
    ("9-11. Evidence ids", "evidence_ids"),
    ("9-11. Facet coverage", "facet_coverage"),
    ("13. Evidence used in prompt", "evidence_used"),
    ("13. Evidence dropped for budget", "evidence_dropped_for_budget"),
    ("15. Inline answer citations", "inline_answer_citations"),
    ("15. Evidence not cited inline", "uncited_inline_evidence"),
    ("15. Answer citations", "answer_citations"),
    ("15. Uncited prompt evidence", "uncited_evidence"),
    ("15. Answer citation coverage", "answer_citation_coverage"),
    ("12. Retrieval confidence", "retrieval_confidence"),
    ("12. Guardrail decision", "guardrail"),
    ("13. Prompt version", "prompt_version"),
]


def format_citations(citations: list[Citation]) -> str:
    """Render citations as a markdown list; link the tag to source_url when present."""
    lines = []
    for c in citations:
        lines.append(f"- [{c.tag}]({c.source_url})" if c.source_url else f"- {c.tag}")
    return "\n".join(lines)


def debug_blocks(trace: dict) -> list[tuple[str, object]]:
    """Ordered (label, value) blocks from a pipeline trace, skipping absent stages."""
    return [(label, trace[key]) for label, key in _TRACE_ORDER if key in (trace or {})]


def stream_chunks(text: str, *, chunk_size: int = 140) -> Iterator[str]:
    """Yield markdown in small chunks for a typewriter-style reveal."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    for i in range(0, len(text), chunk_size):
        yield text[i:i + chunk_size]


def _inject_theme() -> None:
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


def _run_query_with_progress(question: str):
    status = st.empty()
    progress = st.progress(0)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run_query, question)
        step = 0
        while not future.done():
            msg = _PROGRESS_MESSAGES[min(step, len(_PROGRESS_MESSAGES) - 1)]
            progress.progress(min(92, 8 + step * 12))
            status.markdown(f"<div class='progress-card'>{msg}</div>", unsafe_allow_html=True)
            time.sleep(0.7)
            step += 1
        result = future.result()
    progress.progress(100)
    status.markdown("<div class='progress-card'>Answer ready</div>", unsafe_allow_html=True)
    time.sleep(0.25)
    status.empty()
    progress.empty()
    return result


def _render_streamed_markdown(markdown: str, *, enabled: bool = True) -> None:
    if not enabled:
        st.markdown(markdown)
        return
    placeholder = st.empty()
    rendered = ""
    for chunk in stream_chunks(markdown):
        rendered += chunk
        placeholder.markdown(rendered)
        time.sleep(0.018)


def _render_hero() -> None:
    st.markdown(
        """
        <div class="app-hero">
          <div class="eyebrow">Private Equity SEC Intelligence</div>
          <h1 class="hero-title">PE-RAG Analyst Workbench</h1>
          <div class="hero-copy">Ask a business question and review the cited filing evidence.</div>
          <div class="metric-strip">
            <div class="mini-metric"><span>Hit@K</span><strong>1.00</strong></div>
            <div class="mini-metric"><span>MRR</span><strong>1.00</strong></div>
            <div class="mini-metric"><span>Citation Coverage</span><strong>1.00</strong></div>
            <div class="mini-metric"><span>Indexed Chunks</span><strong>60,029</strong></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render() -> None:  # pragma: no cover - exercised via `streamlit run`, not unit tests
    st.set_page_config(page_title="PE-RAG", layout="wide", initial_sidebar_state="expanded")
    _inject_theme()
    _render_hero()

    with st.sidebar:
        st.subheader("Controls")
        debug = st.toggle("Developer trace", value=True)
        stream_answer = st.toggle("Stream answer reveal", value=True)
        st.divider()
        st.caption("Examples")
        for i, sample in enumerate(_SAMPLE_QUERIES, start=1):
            if st.button(sample, key=f"sample_{i}", width="stretch"):
                st.session_state["question"] = sample

    if "question" not in st.session_state:
        st.session_state["question"] = ""

    question = st.text_area(
        "Business question",
        key="question",
        height=92,
        placeholder="Compare Apple and Tesla risk factors in 2024",
    )

    if st.button("Answer", type="primary", icon=":material/arrow_forward:", width="stretch") and question:
        result = _run_query_with_progress(question)
        st.session_state["last_result"] = result
        st.session_state["last_question"] = question

        if result.refused:
            st.warning(result.answer.answer)
        else:
            st.markdown("<div class='answer-label'>Answer</div>", unsafe_allow_html=True)
            _render_streamed_markdown(result.answer.answer, enabled=stream_answer)
            conf = result.guardrail.confidence if result.guardrail else ""
            if conf:
                st.caption(f"Confidence: {conf}")

        if result.answer.sources:
            st.markdown("<div class='source-label'>Sources</div>", unsafe_allow_html=True)
            st.markdown(format_citations(result.answer.sources))

        if debug:
            st.markdown("<div class='debug-label'>Debug Trace</div>", unsafe_allow_html=True)
            for label, value in debug_blocks(result.trace):
                with st.expander(label):
                    st.write(value)

    result = st.session_state.get("last_result")
    if result:
        with st.expander("Analyst feedback"):
            rating = st.radio("Rating", ["Useful", "Needs correction"], horizontal=True)
            citations_correct = st.checkbox("Citations are correct", value=True)
            citation_correction = st.text_area("Citation correction", height=80)
            comment = st.text_area("Analyst note", height=80)
            if st.button("Save feedback"):
                record = feedback.build_feedback_record(
                    question=st.session_state.get("last_question", ""),
                    rating=rating,
                    citations_correct=citations_correct,
                    citation_correction=citation_correction,
                    comment=comment,
                    trace=result.trace,
                )
                path = feedback.write_feedback(record)
                st.success(f"Saved feedback to {path}")


if __name__ == "__main__":
    render()

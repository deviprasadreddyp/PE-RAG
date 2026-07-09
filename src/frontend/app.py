"""Stage 18 — Streamlit debug UI.

A single page that shows both the grounded answer AND the full deterministic pipeline, stage by
stage: parsed intent -> metadata -> hard filter -> plan -> vector ids -> bm25 ids -> RRF -> rerank
-> evidence -> guardrail -> prompt version -> answer, with clickable citations. This is what makes
the "everything before the LLM is deterministic" story visible and auditable.

Run:  ``streamlit run src/frontend/app.py``

The display helpers (``format_citations`` / ``debug_blocks``) are pure functions (no Streamlit) so
they're unit-testable; the ``render`` UI is invoked only when Streamlit runs the file.
"""

from __future__ import annotations

import streamlit as st

from src.retrieval.retrieval_pipeline import run_query
from src.schemas import Citation

# Trace keys rendered in pipeline order (label, trace-key).
_TRACE_ORDER: list[tuple[str, str]] = [
    ("1. Query (validated)", "query"),
    ("2. Intents", "intents"),
    ("3. Companies / years", "companies"),
    ("4. Hard filter", "filter"),
    ("5. Retrieval plan", "plan"),
    ("5. Section boosts", "section_boosts"),
    ("6. Vector candidate ids", "vector_ids"),
    ("6. BM25 candidate ids", "bm25_ids"),
    ("7. RRF-fused ids", "rrf_ids"),
    ("8. Reranked ids", "reranked_ids"),
    ("9-11. Evidence ids", "evidence_ids"),
    ("13. Evidence used in prompt", "evidence_used"),
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


def render() -> None:  # pragma: no cover — exercised via `streamlit run`, not unit tests
    st.set_page_config(page_title="PE-RAG", layout="wide")
    st.title("PE-RAG — SEC filings Q&A")
    st.caption("Deterministic retrieval + exactly one grounded Claude call.")

    with st.sidebar:
        debug = st.toggle("Debug mode", value=True)
        st.markdown("Ask about the corpus's 54 large-cap issuers (10-K / 10-Q, 2022-2026).")

    question = st.text_input("Your question", placeholder="Compare Apple and Tesla risk factors in 2024")

    if st.button("Answer", type="primary") and question:
        with st.spinner("Retrieving evidence and generating a grounded answer…"):
            result = run_query(question)

        if result.refused:
            st.warning(result.answer.answer)
        else:
            st.markdown(result.answer.answer)
            conf = result.guardrail.confidence if result.guardrail else ""
            if conf:
                st.caption(f"Confidence: {conf}")

        if result.answer.sources:
            st.subheader("Citations")
            st.markdown(format_citations(result.answer.sources))

        if debug:
            st.subheader("Debug trace — the deterministic pipeline")
            for label, value in debug_blocks(result.trace):
                with st.expander(label):
                    st.write(value)


if __name__ == "__main__":
    render()

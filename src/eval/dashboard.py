"""Evaluation dashboard (Streamlit) — read data/logs/eval_report.json and visualize it.

One page answers Matt's question — *"if you changed chunking/top-k/prompt/reranker tomorrow, how
would you know if it got better or worse?"* — with an Overview, the Retrieval A/B comparison, RAGAS
generation scores, a regression banner vs the previous run, and a per-case inspector.

Run:  ``streamlit run src/eval/dashboard.py``  (after ``python -m src.eval.run_eval``)

Data extraction lives in ``report.py`` (pure, unit-tested); this module only renders.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.config import settings
from src.eval import report as report_mod


def render() -> None:  # pragma: no cover — exercised via `streamlit run`, not unit tests
    st.set_page_config(page_title="PE-RAG Evaluation", layout="wide")
    st.title("PE-RAG — Evaluation Dashboard")

    report = report_mod.load_previous(settings.data_path / "logs")
    if not report:
        st.warning("No eval_report.json yet. Run:  python -m src.eval.run_eval")
        return

    reg = report.get("regression")
    if reg is not None:
        (st.success if reg["ok"] else st.error)(
            "No regressions vs previous run." if reg["ok"]
            else f"{len(reg['regressions'])} regression(s) vs previous run.")

    st.subheader("Overview")
    cols = st.columns(max(len(report_mod.dashboard_overview(report)), 1))
    for col, (name, val) in zip(cols, report_mod.dashboard_overview(report).items()):
        col.metric(name, f"{val:.3f}" if isinstance(val, float) else val)

    tab_ab, tab_ragas, tab_cases = st.tabs(["Retrieval A/B", "Generation (RAGAS)", "Per-case"])

    with tab_ab:
        recall = report_mod.ab_recall_by_mode(report)
        if recall:
            st.caption("Recall@k by retrieval strategy — the evidence for choosing hybrid + rerank.")
            st.bar_chart(recall)
            st.dataframe((report.get("ab") or {}).get("summary"))
        else:
            st.info("No A/B section in this report.")

    with tab_ragas:
        ragas = (report.get("ragas") or {}).get("summary")
        st.dataframe(ragas) if ragas else st.info("RAGAS not run (needs `pip install ragas` + key).")

    with tab_cases:
        cases = (report.get("retrieval") or {}).get("cases") or []
        if cases:
            labels = [f'{c.get("id", "?")} — {c["question"]}' for c in cases]
            pick = st.selectbox("Question", range(len(cases)), format_func=lambda i: labels[i])
            st.json(cases[pick])
            st.caption("For live per-query inspection (retrieved chunks, prompt, answer), use the "
                       "debug UI: streamlit run src/frontend/app.py")
        else:
            st.info("No per-case rows.")


if __name__ == "__main__":
    render()

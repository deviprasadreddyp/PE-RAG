"""Evaluation dashboard (Streamlit).

Read ``data/logs/eval_report.json`` and render a usable inspection surface for
retrieval quality, retrieval A/B comparisons, generation grading, regressions,
and per-case failures. The dashboard is deliberately read-only: eval execution
stays in ``python -m src.eval.run_eval`` so opening the UI never re-runs queries,
embeddings, retrieval, or LLM calls.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from src.config import settings
from src.eval import report as report_mod

REPORT_NAME = "eval_report.json"

_THEME_CSS = """
<style>
:root {
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
    radial-gradient(circle at 16% 4%, rgba(255, 199, 220, 0.34), transparent 28%),
    linear-gradient(135deg, #fff8fb 0%, #fff1f6 42%, #f8fbff 100%);
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

.dashboard-hero {
  border: 1px solid rgba(234, 215, 223, 0.9);
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(255,255,255,0.94), rgba(255,241,246,0.88));
  box-shadow: 0 18px 50px rgba(159, 35, 79, 0.10);
  padding: 1.15rem 1.25rem;
  margin-bottom: 1rem;
}

.dashboard-hero h1 {
  color: var(--ink);
  font-size: 2rem;
  line-height: 1.1;
  font-weight: 780;
  margin: 0;
}

.dashboard-hero p {
  color: var(--muted);
  margin: 0.35rem 0 0;
}

[data-testid="stMetric"] {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: rgba(255,255,255,0.84);
  padding: 0.8rem;
}

.stButton > button {
  border-radius: 10px;
  border: 1px solid var(--rose-200);
  background: linear-gradient(135deg, #d9467c, #9f234f);
  color: #ffffff;
  font-weight: 720;
}

[data-testid="stDataFrame"], [data-testid="stExpander"] {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: rgba(255,255,255,0.78);
}
</style>
"""

_CASE_COLUMNS = [
    "id",
    "question",
    "status",
    "precision@k",
    "hit@k",
    "mrr",
    "ndcg@k",
    "company_recall",
    "citation_groundedness",
    "citation_coverage",
    "refusal_correct",
]


def report_path(out_dir: str | Path | None = None) -> Path:
    """Default eval report path."""
    return (Path(out_dir) if out_dir is not None else settings.data_path / "logs") / REPORT_NAME


def load_report(path: str | Path | None = None) -> dict | None:
    """Load a report from disk, returning None when no report exists."""
    p = Path(path) if path is not None else report_path()
    return json.loads(p.read_text("utf-8")) if p.exists() else None


def _num(value: Any) -> float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _fmt(value: Any) -> str:
    n = _num(value)
    if n is not None:
        return f"{n:.3f}" if isinstance(value, float) else str(value)
    if value is None:
        return ""
    return str(value)


def metric_cards(report: dict) -> dict[str, Any]:
    """Headline dashboard cards."""
    ret = (report.get("retrieval") or {}).get("summary") or {}
    cases = (report.get("retrieval") or {}).get("cases") or []
    ab = (report.get("ab") or {}).get("summary") or {}
    ragas = (report.get("ragas") or {}).get("summary") or {}
    answered = sum(1 for c in cases if not c.get("refused"))
    refused = sum(1 for c in cases if c.get("refused"))

    cards: dict[str, Any] = {
        "cases": ret.get("n_cases", len(cases)),
        "answered": answered,
        "refused": refused,
    }
    for key in ("precision@k", "hit@k", "mrr", "ndcg@k", "company_recall"):
        if key in ret:
            cards[key] = ret[key]
    if "hybrid" in ab and "recall@k" in ab["hybrid"]:
        cards["hybrid recall@k"] = ab["hybrid"]["recall@k"]
    for key in ("faithfulness", "answer_relevancy"):
        if key in ragas:
            cards[key] = ragas[key]
    return cards


def ab_summary_rows(report: dict) -> list[dict]:
    """Rows for the retrieval strategy comparison table."""
    summary = (report.get("ab") or {}).get("summary") or {}
    return [{"strategy": mode, **metrics} for mode, metrics in summary.items()]


def ab_chart_frame(report: dict, metric: str) -> pd.DataFrame:
    """Data frame indexed by strategy for a selected A/B metric."""
    rows = ab_summary_rows(report)
    data = [
        {"strategy": row["strategy"], metric: row.get(metric, 0.0)}
        for row in rows
        if metric in row
    ]
    if not data:
        return pd.DataFrame(columns=[metric])
    return pd.DataFrame(data).set_index("strategy")


def case_rows(report: dict) -> list[dict]:
    """Normalize per-case records for table display."""
    rows = []
    for case in (report.get("retrieval") or {}).get("cases") or []:
        row = {}
        for col in _CASE_COLUMNS:
            if col == "status":
                continue
            value = case.get(col, "")
            row[col] = value if col in {"id", "question"} else _fmt(value)
        row["status"] = "refused" if case.get("refused") else "answered"
        rows.append(row)
    return rows


def filter_cases(rows: list[dict], *, query: str = "", status: str = "all") -> list[dict]:
    """Filter case table rows by search text and answer/refusal status."""
    q = query.strip().lower()
    out = []
    for row in rows:
        if status != "all" and row.get("status") != status:
            continue
        haystack = f"{row.get('id', '')} {row.get('question', '')}".lower()
        if q and q not in haystack:
            continue
        out.append(row)
    return out


def case_by_id(report: dict) -> dict[str, dict]:
    """Original per-case records by id, for raw detail panes."""
    return {
        str(case.get("id", "")): case
        for case in (report.get("retrieval") or {}).get("cases") or []
        if case.get("id")
    }


def regression_rows(report: dict, key: str) -> list[dict]:
    """Regression/improvement rows, if this report compared against a prior one."""
    reg = report.get("regression") or {}
    return list(reg.get(key) or [])


def _metric_grid(cards: dict[str, Any]) -> None:
    cols = st.columns(min(max(len(cards), 1), 6))
    for i, (name, value) in enumerate(cards.items()):
        cols[i % len(cols)].metric(name, _fmt(value))


def _inject_theme() -> None:
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


def _render_hero() -> None:
    st.markdown(
        """
        <div class="dashboard-hero">
          <h1>Evaluation Dashboard</h1>
          <p>Quality, regressions, and per-case evidence checks for the SEC filings RAG.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_sidebar(path: Path) -> None:
    with st.sidebar:
        st.header("Report")
        st.code(str(path))
        if path.exists():
            updated = datetime.fromtimestamp(path.stat().st_mtime)
            st.caption(f"Updated {updated:%Y-%m-%d %H:%M:%S}")
        st.button("Refresh report", icon=":material/refresh:")


def _render_overview(report: dict) -> None:
    _metric_grid(metric_cards(report))

    reg = report.get("regression")
    if reg:
        if reg.get("ok"):
            st.success("No metric regressions versus the previous report.")
        else:
            st.error(f"{len(regression_rows(report, 'regressions'))} metric regressions detected.")

        left, right = st.columns(2)
        with left:
            st.subheader("Regressions")
            rows = regression_rows(report, "regressions")
            st.dataframe(rows, width="stretch", hide_index=True) if rows else st.info("None")
        with right:
            st.subheader("Improvements")
            rows = regression_rows(report, "improvements")
            st.dataframe(rows, width="stretch", hide_index=True) if rows else st.info("None")


def _render_ab(report: dict) -> None:
    rows = ab_summary_rows(report)
    if not rows:
        st.info("No retrieval A/B results in this report.")
        return

    metric = st.segmented_control(
        "Metric",
        options=["recall@k", "precision@k", "mrr", "ndcg@k"],
        default="recall@k",
    )
    frame = ab_chart_frame(report, metric)
    if not frame.empty:
        st.bar_chart(frame, width="stretch")
    st.dataframe(rows, width="stretch", hide_index=True)

    per_case = (report.get("ab") or {}).get("per_case") or []
    if per_case:
        with st.expander("Per-case A/B details"):
            labels = [str(row.get("id", "?")) for row in per_case]
            pick = st.selectbox("Case", labels)
            selected = next(row for row in per_case if str(row.get("id", "?")) == pick)
            st.json(selected)


def _render_cases(report: dict) -> None:
    rows = case_rows(report)
    if not rows:
        st.info("No per-case rows in this report.")
        return

    controls = st.columns([2, 1])
    query = controls[0].text_input("Search cases", "")
    status = controls[1].selectbox("Status", ["all", "answered", "refused"])
    filtered = filter_cases(rows, query=query, status=status)

    st.dataframe(filtered, width="stretch", hide_index=True)

    by_id = case_by_id(report)
    if filtered and by_id:
        ids = [str(row["id"]) for row in filtered if row.get("id") in by_id]
        if ids:
            selected_id = st.selectbox("Inspect case", ids)
            st.json(by_id[selected_id])


def _render_ragas(report: dict) -> None:
    ragas = report.get("ragas")
    if not ragas:
        st.info("No RAGAS generation grading in this report.")
        return
    summary = ragas.get("summary") if isinstance(ragas, dict) else None
    st.dataframe(summary or ragas, width="stretch")


def render() -> None:  # pragma: no cover - exercised via `streamlit run`, not unit tests
    st.set_page_config(page_title="PE-RAG Evaluation", layout="wide")
    _inject_theme()
    path = report_path()
    _render_sidebar(path)

    _render_hero()
    report = load_report(path)
    if not report:
        st.warning("No eval report found.")
        st.code("python -m src.eval.run_eval")
        return

    tabs = st.tabs(["Overview", "Retrieval A/B", "Cases", "Generation", "Raw"])
    with tabs[0]:
        _render_overview(report)
    with tabs[1]:
        _render_ab(report)
    with tabs[2]:
        _render_cases(report)
    with tabs[3]:
        _render_ragas(report)
    with tabs[4]:
        st.json(report)


if __name__ == "__main__":
    render()

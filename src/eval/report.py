"""Evaluation reports (JSON + self-contained HTML) + regression comparison.

``write_reports`` persists ``eval_report.json`` and a shareable ``eval_report.html``.
``compare_to_previous`` diffs the current summary against the last run and flags **regressions**
(a metric dropped beyond tolerance) — so a change to chunking / top-k / prompt / reranker is judged
objectively, not by intuition. No external deps (inline HTML/CSS).
"""

from __future__ import annotations

import html
import json
from pathlib import Path

REGRESSION_TOLERANCE = 0.02        # a metric drop larger than this is a regression
LOWER_IS_BETTER = ("latency", "cost", "tokens")


def flat_summary(report: dict) -> dict:
    """Flatten a report's headline metrics into one dict for comparison."""
    out: dict[str, float] = {}
    for k, v in (report.get("retrieval", {}).get("summary") or {}).items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = v
    for mode, metrics in (report.get("ab", {}) or {}).get("summary", {}).items():
        for m, v in metrics.items():
            out[f"ab.{mode}.{m}"] = v
    for m, v in ((report.get("ragas", {}) or {}).get("summary") or {}).items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[f"ragas.{m}"] = v
    return out


def compare_to_previous(current: dict, previous: dict, *, tolerance: float = REGRESSION_TOLERANCE
                        ) -> dict:
    """Diff two flat summaries → {ok, regressions[], improvements[]}."""
    regressions, improvements = [], []
    for key, cur in current.items():
        if key not in previous:
            continue
        delta = round(cur - previous[key], 4)
        lower_is_better = any(term in key for term in LOWER_IS_BETTER)
        if lower_is_better:
            if delta > tolerance:
                regressions.append({"metric": key, "prev": previous[key], "cur": cur, "delta": delta})
            elif delta < -tolerance:
                improvements.append({"metric": key, "prev": previous[key], "cur": cur, "delta": delta})
        elif delta < -tolerance:
            regressions.append({"metric": key, "prev": previous[key], "cur": cur, "delta": delta})
        elif delta > tolerance:
            improvements.append({"metric": key, "prev": previous[key], "cur": cur, "delta": delta})
    return {"ok": not regressions, "regressions": regressions, "improvements": improvements}


def load_previous(out_dir: Path) -> dict | None:
    p = Path(out_dir) / "eval_report.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else None


# --- display helpers (pure; used by the Streamlit dashboard) ---------------------

def dashboard_overview(report: dict) -> dict:
    """The few headline numbers for the dashboard's top row."""
    ret = (report.get("retrieval") or {}).get("summary") or {}
    ab = (report.get("ab") or {}).get("summary") or {}
    ragas = (report.get("ragas") or {}).get("summary") or {}
    out: dict[str, float] = {}
    for k in ("precision@k", "mrr", "ndcg@k", "company_recall"):
        if k in ret:
            out[k] = ret[k]
    if ab.get("hybrid", {}).get("recall@k") is not None:
        out["hybrid recall@k"] = ab["hybrid"]["recall@k"]
    for k in ("faithfulness", "answer_relevancy"):
        if ragas.get(k) is not None:
            out[k] = ragas[k]
    return out


def ab_recall_by_mode(report: dict) -> dict:
    """{strategy: recall@k} for the A/B bar chart."""
    ab = (report.get("ab") or {}).get("summary") or {}
    return {mode: m["recall@k"] for mode, m in ab.items() if "recall@k" in m}


def _table(headers: list[str], rows: list[list]) -> str:
    head = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>" for r in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def build_html_report(report: dict) -> str:
    """Render a self-contained HTML evaluation report."""
    parts = ["<h1>PE-RAG — Evaluation Report</h1>"]

    ret = (report.get("retrieval") or {}).get("summary") or {}
    if ret:
        parts.append("<h2>Overall (generation path)</h2>")
        parts.append(_table(["metric", "value"], [[k, v] for k, v in ret.items()]))

    ab = (report.get("ab") or {}).get("summary")
    if ab:
        parts.append("<h2>Retrieval A/B — strategy comparison</h2>")
        metric_names = sorted({m for d in ab.values() for m in d})
        rows = [[mode] + [ab[mode].get(m, "") for m in metric_names] for mode in ab]
        parts.append(_table(["strategy"] + metric_names, rows))

    ragas = (report.get("ragas") or {}).get("summary")
    if ragas:
        parts.append("<h2>Generation quality (RAGAS)</h2>")
        parts.append(_table(["metric", "value"], [[k, v] for k, v in ragas.items()]))

    reg = report.get("regression")
    if reg:
        status = "✅ no regressions" if reg["ok"] else "⚠️ REGRESSIONS"
        parts.append(f"<h2>Regression vs previous run: {status}</h2>")
        if reg["regressions"]:
            parts.append(_table(["metric", "prev", "cur", "delta"],
                                [[r["metric"], r["prev"], r["cur"], r["delta"]] for r in reg["regressions"]]))

    cases = (report.get("retrieval") or {}).get("cases") or []
    if cases:
        parts.append("<h2>Per-case</h2>")
        cols = ["id", "question", "precision@k", "mrr", "ndcg@k", "company_recall", "refused"]
        rows = [[c.get(col, "") for col in cols] for c in cases]
        parts.append(_table(cols, rows))

    style = ("<style>body{font-family:system-ui,sans-serif;margin:2rem;max-width:1000px}"
             "table{border-collapse:collapse;margin:1rem 0;width:100%}"
             "th,td{border:1px solid #ccc;padding:6px 10px;text-align:left;font-size:14px}"
             "th{background:#f4f4f4}h2{margin-top:2rem}</style>")
    return f"<!doctype html><meta charset='utf-8'><title>PE-RAG Eval</title>{style}" + "".join(parts)


def write_reports(report: dict, out_dir: str | Path) -> dict:
    """Write eval_report.json + eval_report.html; return their paths."""
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    json_path = d / "eval_report.json"
    html_path = d / "eval_report.html"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    html_path.write_text(build_html_report(report), encoding="utf-8")
    return {"json": str(json_path), "html": str(html_path)}

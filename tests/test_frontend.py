"""P20 smoke tests: pure display helpers (citations markdown, ordered debug blocks)."""

import pytest

pytest.importorskip("streamlit")                       # UI module imports streamlit at top

from src.frontend import app  # noqa: E402
from src.schemas import Citation  # noqa: E402


def test_format_citations_links_when_url_present():
    cites = [
        Citation(tag="[AAPL 10-K FY2024 · Risk Factors]", source_url="https://sec.gov/AAPL"),
        Citation(tag="[TSLA 10-K FY2024 · Business]"),          # no url
    ]
    md = app.format_citations(cites)
    assert "[[AAPL 10-K FY2024 · Risk Factors]](https://sec.gov/AAPL)" in md
    assert "- [TSLA 10-K FY2024 · Business]" in md              # plain (no link)


def test_debug_blocks_ordered_and_skips_absent():
    trace = {"query": "Apple risk", "intents": ["Risk"], "plan": "global",
             "vector_ids": ["a"], "guardrail": {"ok": True}}
    blocks = app.debug_blocks(trace)
    labels = [lbl for lbl, _ in blocks]
    # pipeline order preserved; absent keys (e.g. bm25_ids) skipped
    assert labels.index("1. Query (validated)") < labels.index("2. Intents") < labels.index("5. Retrieval plan")
    assert "6. BM25 candidate ids" not in labels
    assert ("2. Intents", ["Risk"]) in blocks


def test_render_is_callable():
    assert callable(app.render)

"""EV5 smoke test: the eval dashboard imports and exposes a callable render (skips if no streamlit)."""

import pytest

pytest.importorskip("streamlit")

from src.eval import dashboard  # noqa: E402


def test_render_is_callable():
    assert callable(dashboard.render)

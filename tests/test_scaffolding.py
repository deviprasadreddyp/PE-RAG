"""Commit 1 scaffolding checks: the package tree imports and the data stage folders exist."""

import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGES = ["raw", "cleaned", "metadata", "sections", "chunks", "embeddings", "vectorstore", "logs"]


def test_src_packages_import():
    for mod in ("src", "src.pipeline", "src.retrieval", "src.generation"):
        assert importlib.import_module(mod) is not None


def test_src_has_version():
    import src

    assert isinstance(src.__version__, str) and src.__version__


def test_data_stage_dirs_exist():
    for stage in STAGES:
        assert (ROOT / "data" / stage).is_dir(), f"missing data/{stage}"

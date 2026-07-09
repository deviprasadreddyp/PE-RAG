"""Observability tests: round-trips (json/txt/pydantic), dir creation, idempotency, listing, safety."""

import pytest

from src.observability import (
    artifact_path,
    list_artifacts,
    load_artifact,
    persist_artifact,
    run_docs,
    stage_count,
)
from src.schemas import Chunk, DocMetadata


def _chunk(i: int = 0) -> Chunk:
    return Chunk.from_metadata(
        DocMetadata(company="Apple Inc", ticker="AAPL", form="10-K",
                    filing_date="2022-10-28", source_file="AAPL_10K_2022Q3_2022-10-28_full.txt"),
        id=f"AAPL_10K_2024_{i}", doc_id="AAPL_10K_2024", chunk_index=i,
        section="Risk Factors", text=f"body {i}", embed_text=f"enriched {i}",
    )


def test_json_roundtrip_and_dir_creation(tmp_path):
    obj = {"a": 1, "b": ["x", "y"], "n": 3.5}
    p = persist_artifact("metadata", "AAPL_10K_2024", obj, base=tmp_path)
    assert p == tmp_path / "metadata" / "AAPL_10K_2024.json"
    assert p.parent.is_dir()                                   # created on demand
    assert load_artifact("metadata", "AAPL_10K_2024", base=tmp_path) == obj


def test_json_is_pretty_and_unicode_preserved(tmp_path):
    persist_artifact("metadata", "d", {"v": "£100 café"}, base=tmp_path)
    text = artifact_path("metadata", "d", base=tmp_path).read_text("utf-8")
    assert "\n  " in text                                       # indent=2
    assert "£100 café" in text and "\\u" not in text           # ensure_ascii=False


def test_txt_roundtrip_is_byte_faithful(tmp_path):
    body = "Line 1\n\nLine 2 with trailing space \n"
    persist_artifact("cleaned", "d", body, ext="txt", base=tmp_path)
    assert load_artifact("cleaned", "d", ext="txt", base=tmp_path) == body


def test_pydantic_and_list_roundtrip(tmp_path):
    persist_artifact("chunks", "AAPL_10K_2024", _chunk(0), base=tmp_path)
    assert load_artifact("chunks", "AAPL_10K_2024", base=tmp_path) == _chunk(0).model_dump(mode="json")

    chunks = [_chunk(0), _chunk(1)]
    persist_artifact("chunks", "AAPL_10K_2024", chunks, base=tmp_path)
    loaded = load_artifact("chunks", "AAPL_10K_2024", base=tmp_path)
    assert loaded == [c.model_dump(mode="json") for c in chunks]


def test_overwrite_is_idempotent(tmp_path):
    for _ in range(3):
        persist_artifact("metadata", "d", {"k": 1}, base=tmp_path)
    folder = tmp_path / "metadata"
    assert len(list(folder.glob("*.json"))) == 1               # no duplicates
    a = artifact_path("metadata", "d", base=tmp_path).read_text("utf-8")
    persist_artifact("metadata", "d", {"k": 1}, base=tmp_path)
    assert artifact_path("metadata", "d", base=tmp_path).read_text("utf-8") == a  # deterministic


def test_list_and_count(tmp_path):
    persist_artifact("raw", "B", "b", ext="txt", base=tmp_path)
    persist_artifact("raw", "A", "a", ext="txt", base=tmp_path)
    (tmp_path / "raw" / ".gitkeep").write_text("")             # must be ignored
    assert list_artifacts("raw", ext="txt", base=tmp_path) == ["A", "B"]   # sorted
    assert stage_count("raw", ext="txt", base=tmp_path) == 2
    assert list_artifacts("nonexistent", base=tmp_path) == []


def test_missing_artifact_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_artifact("metadata", "missing", base=tmp_path)


def test_list_artifacts_skips_underscore_files(tmp_path):
    persist_artifact("raw", "AAPL", "x", ext="txt", base=tmp_path)
    persist_artifact("raw", "_dead_letter", [{"x": 1}], base=tmp_path)   # json bookkeeping
    persist_artifact("raw", "_notes", "y", ext="txt", base=tmp_path)
    assert list_artifacts("raw", ext="txt", base=tmp_path) == ["AAPL"]


def test_run_docs_isolates_per_doc_failures(tmp_path):
    seen = []

    def fn(d):
        if d == "BAD":
            raise ValueError("boom")
        seen.append(d)
        return d

    rep = run_docs("clean", ["A", "BAD", "C"], fn, base=tmp_path)
    assert rep["ok"] == 2 and rep["failed"] == 1 and seen == ["A", "C"]   # one bad doc didn't stop the rest
    failures = load_artifact("logs", "clean_failures", base=tmp_path)
    assert failures[0]["doc_id"] == "BAD" and "boom" in failures[0]["reason"]


def test_unsafe_tokens_and_bad_ext_rejected(tmp_path):
    with pytest.raises(ValueError):
        artifact_path("metadata", "../escape", base=tmp_path)
    with pytest.raises(ValueError):
        artifact_path("meta/x", "d", base=tmp_path)
    with pytest.raises(ValueError):
        persist_artifact("metadata", "d", {}, ext="csv", base=tmp_path)
    with pytest.raises(TypeError):
        persist_artifact("cleaned", "d", {"not": "a str"}, ext="txt", base=tmp_path)

"""Stage 1 tests: filename validation, byte-faithful raw persistence, dead-lettering."""

import json

from src.observability import load_artifact, list_artifacts
from src.pipeline.ingest import FILENAME, doc_id_for, run_ingest

HEADER = "Company: Apple Inc\nTicker: AAPL\n" + "=" * 60 + "\n"
BODY = (
    "0000320193us-gaap:CommonStockMember\n"
    "UNITED STATES SECURITIES AND EXCHANGE COMMISSION FORM 10-K\n"
    "Risk factors: supply chain.\n"
)
GOOD = "AAPL_10K_2022Q3_2022-10-28_full.txt"


def _corpus(tmp_path, text_files: dict, manifest_files, byte_files: dict | None = None):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for name, content in text_files.items():
        (corpus / name).write_text(content, encoding="utf-8", newline="")   # LF on disk
    for name, raw in (byte_files or {}).items():
        (corpus / name).write_bytes(raw)
    (corpus / "manifest.json").write_text(json.dumps({"files": manifest_files}), encoding="utf-8")
    return corpus


def test_filename_regex():
    assert FILENAME.match("AAPL_10K_2022Q3_2022-10-28_full.txt")
    assert FILENAME.match("AAPL_10K_2025-10-31_full.txt")            # no period
    assert FILENAME.match("BRK_10K_2025-02-24_full.txt")
    assert not FILENAME.match("AAPL_10K_2022Q3_2022-10-28.txt")      # missing _full
    assert not FILENAME.match("manifest.json")


def test_doc_id_for():
    assert doc_id_for(GOOD) == "AAPL_10K_2022Q3_2022-10-28"


def test_ingest_is_byte_faithful_and_deadletters(tmp_path):
    content = HEADER + BODY
    corpus = _corpus(
        tmp_path,
        text_files={GOOD: content},
        byte_files={"TSLA_10K_2023-01-01_full.txt": b"\xff\xfe\x00 not utf-8"},
        manifest_files=[
            GOOD,
            "BADNAME.txt",                              # invalid filename
            "MSFT_10K_2024-01-01_full.txt",             # missing file
            "TSLA_10K_2023-01-01_full.txt",             # bad UTF-8
        ],
    )
    out = tmp_path / "out"
    report = run_ingest(corpus, base=out)

    assert report["ingested"] == 1
    assert report["failed"] == 3

    # content preserved exactly, and XBRL NOT stripped at this stage
    loaded = load_artifact("raw", doc_id_for(GOOD), ext="txt", base=out)
    assert loaded == content and "us-gaap:CommonStockMember" in loaded

    # byte-identical to source (LF source, byte-faithful write)
    src = (corpus / GOOD).read_bytes()
    dst = (out / "raw" / f"{doc_id_for(GOOD)}.txt").read_bytes()
    assert dst == src

    # dead-letter recorded with reasons
    reasons = {d["file"]: d["reason"] for d in load_artifact("raw", "_dead_letter", base=out)}
    assert reasons["BADNAME.txt"] == "invalid filename"
    assert reasons["MSFT_10K_2024-01-01_full.txt"] == "missing file"
    assert reasons["TSLA_10K_2023-01-01_full.txt"].startswith("not valid UTF-8")

    # the dead-letter json is not mistaken for a raw filing (txt listing)
    assert list_artifacts("raw", ext="txt", base=out) == [doc_id_for(GOOD)]


def test_deadletter_written_empty_when_all_ok(tmp_path):
    corpus = _corpus(tmp_path, {GOOD: "hi"}, [GOOD])
    out = tmp_path / "out"
    report = run_ingest(corpus, base=out)
    assert report["failed"] == 0
    assert load_artifact("raw", "_dead_letter", base=out) == []

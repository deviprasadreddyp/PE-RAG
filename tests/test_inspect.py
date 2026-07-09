"""Inspect tests: passes after a full build, pending mid-build, detects XBRL leak + missing embed_text."""

import json

from src.inspect import main, run_inspect
from src.observability import list_artifacts, load_artifact, persist_artifact
from src.run import run

BODY = (
    "0000320193us-gaap:Foo\n"
    "UNITED STATES SECURITIES AND EXCHANGE COMMISSION FORM 10-K\n"
    "Item 1.\xa0\xa0\xa0\xa0BusinessThe Company designs products. " + ("context " * 200)
    + "Item 1A.\xa0\xa0\xa0\xa0Risk FactorsThe Company faces risks. " + ("risk " * 200)
)


class FakeEmbedder:
    model = "fake-embed"

    def embed_documents(self, texts):
        return [[float(len(t)), 1.0, 2.0] for t in texts]

    def embed_query(self, text):
        return [float(len(text)), 1.0, 2.0]


def _corpus(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for ticker, date in [("AAPL", "2022-10-28"), ("MSFT", "2024-07-30")]:
        header = (f"Company: {ticker} Inc\nTicker: {ticker}\nFiling Type: 10-K\n"
                  f"Filing Date: {date}\n" + "=" * 60 + "\n")
        (corpus / f"{ticker}_10K_2022Q3_{date}_full.txt").write_text(header + BODY, encoding="utf-8", newline="")
    (corpus / "manifest.json").write_text(
        json.dumps({"files": ["AAPL_10K_2022Q3_2022-10-28_full.txt", "MSFT_10K_2022Q3_2024-07-30_full.txt"]}),
        encoding="utf-8")
    return corpus


def _check(res, name):
    return next(c for c in res["checks"] if c.name == name)


def test_inspect_passes_after_full_build(tmp_path):
    out = tmp_path / "out"
    run(stage="all", corpus_dir=_corpus(tmp_path), base=out, embedder=FakeEmbedder())
    res = run_inspect(base=out)
    assert res["ok"] is True
    assert all(c.ok for c in res["checks"])
    assert res["counts"]["embeddings"] == res["counts"]["chunks"]
    assert res["counts"]["chroma"] == res["counts"]["chunks"]
    assert main(base=out) == 0


def test_inspect_pending_when_embed_not_run(tmp_path):
    out = tmp_path / "out"
    corpus = _corpus(tmp_path)
    for s in ("ingest", "clean", "metadata", "sections", "chunk", "enrich"):
        run(stage=s, corpus_dir=corpus, base=out)
    res = run_inspect(base=out)
    assert res["ok"] is True                                   # deterministic checks pass
    assert "pending" in _check(res, "embeddings==chunks").detail
    assert "pending" in _check(res, "chroma==chunks").detail
    assert res["counts"]["chroma"] is None


def test_inspect_detects_xbrl_leak(tmp_path):
    out = tmp_path / "out"
    corpus = _corpus(tmp_path)
    for s in ("ingest", "clean", "metadata", "sections", "chunk", "enrich"):
        run(stage=s, corpus_dir=corpus, base=out)
    doc = list_artifacts("cleaned", "txt", base=out)[0]
    persist_artifact("cleaned", doc, "leaked 0000320193us-gaap:CommonStock line", ext="txt", base=out)
    res = run_inspect(base=out)
    assert res["ok"] is False and _check(res, "cleaned:no-xbrl").ok is False
    assert main(base=out) == 1


def test_inspect_detects_missing_embed_text(tmp_path):
    out = tmp_path / "out"
    corpus = _corpus(tmp_path)
    for s in ("ingest", "clean", "metadata", "sections", "chunk", "enrich"):
        run(stage=s, corpus_dir=corpus, base=out)
    doc = list_artifacts("chunks", base=out)[0]
    chunks = load_artifact("chunks", doc, base=out)
    chunks[0]["embed_text"] = ""                               # break enrichment on one chunk
    persist_artifact("chunks", doc, chunks, base=out)
    res = run_inspect(base=out)
    assert res["ok"] is False and _check(res, "chunks:embed_text-set").ok is False

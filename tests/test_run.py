"""Orchestrator tests: `all` produces every artifact; re-run is a no-op; --force redoes; single stage."""

import json

from src.observability import load_artifact, stage_count
from src.pipeline.store import ChromaVectorStore
from src.run import run

BODY = (
    "0000320193us-gaap:Foo\n"
    "UNITED STATES SECURITIES AND EXCHANGE COMMISSION FORM 10-K\n"
    "Item 1.\xa0\xa0\xa0\xa0BusinessThe Company designs products. " + ("context " * 200)
    + "Item 1A.\xa0\xa0\xa0\xa0Risk FactorsThe Company faces risks. " + ("risk " * 200)
)
FILES = {
    "AAPL_10K_2022Q3_2022-10-28_full.txt": "AAPL",
    "MSFT_10K_2022Q3_2024-07-30_full.txt": "MSFT",
}


class FakeEmbedder:
    model = "fake-embed"

    def embed_documents(self, texts):
        return [[float(len(t)), float(sum(map(ord, t)) % 100), 1.0] for t in texts]

    def embed_query(self, text):
        return [float(len(text)), float(sum(map(ord, text)) % 100), 1.0]


def _corpus(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for fname, ticker in FILES.items():
        date = fname.split("_")[3]
        header = (f"Company: {ticker} Inc\nTicker: {ticker}\nFiling Type: 10-K\n"
                  f"Filing Date: {date}\n" + "=" * 60 + "\n")
        (corpus / fname).write_text(header + BODY, encoding="utf-8", newline="")
    (corpus / "manifest.json").write_text(json.dumps({"files": list(FILES)}), encoding="utf-8")
    return corpus


def test_all_produces_every_artifact_then_noop_then_force(tmp_path):
    corpus, out = _corpus(tmp_path), tmp_path / "out"

    rep1 = run(stage="all", corpus_dir=corpus, base=out, embedder=FakeEmbedder())
    # every stage's data/<stage>/ folder is populated
    for stg, ext in [("raw", "txt"), ("cleaned", "txt"), ("metadata", "json"),
                     ("sections", "json"), ("chunks", "json"), ("embeddings", "json")]:
        assert stage_count(stg, ext, base=out) == 2, stg
    assert (out / "vectorstore" / "bm25.json").exists()
    total_chunks = sum(len(load_artifact("chunks", d, base=out)) for d in load_artifact_ids(out))
    assert ChromaVectorStore(persist_dir=out / "vectorstore").count() == total_chunks
    assert all(rep1[s]["ran"] > 0 for s in rep1)                 # everything ran

    rep2 = run(stage="all", corpus_dir=corpus, base=out, embedder=FakeEmbedder())
    assert all(rep2[s]["ran"] == 0 for s in rep2)                # no-op: all skipped

    rep3 = run(stage="all", corpus_dir=corpus, base=out, embedder=FakeEmbedder(), force=True)
    assert all(rep3[s]["ran"] > 0 for s in rep3)                 # --force redoes everything


def load_artifact_ids(out):
    from src.observability import list_artifacts
    return list_artifacts("chunks", base=out)


def test_single_stage_and_doc_id(tmp_path):
    corpus, out = _corpus(tmp_path), tmp_path / "out"
    run(stage="ingest", corpus_dir=corpus, base=out)
    assert stage_count("raw", "txt", base=out) == 2 and stage_count("cleaned", "txt", base=out) == 0

    doc = "AAPL_10K_2022Q3_2022-10-28"
    rep = run(stage="clean", doc_id=doc, base=out)
    assert rep["clean"]["ran"] == 1
    assert stage_count("cleaned", "txt", base=out) == 1          # only the one doc cleaned


def test_unknown_stage_raises():
    import pytest
    with pytest.raises(ValueError):
        run(stage="bogus")

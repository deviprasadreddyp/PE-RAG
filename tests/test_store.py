"""Stage 8 tests: Chroma upsert count, idempotency, metadata where-query, BM25 persistence + hits."""

from src.observability import persist_artifact
from src.pipeline.store import Bm25Index, ChromaVectorStore, run_store, tokenize
from src.schemas import Chunk, DocMetadata


def _chunk(ticker: str, i: int, text: str) -> Chunk:
    return Chunk.from_metadata(
        DocMetadata(company=f"{ticker} Inc", ticker=ticker, form="10-K", filing_date="2022-10-28",
                    source_file=f"{ticker}_10K_2024_full.txt", fiscal_period="2022Q3", year=2022),
        id=f"{ticker}_10K_2024_{i}", doc_id=f"{ticker}_10K_2024", chunk_index=i,
        section="Risk Factors", text=text,
    )


def _seed(base):
    aapl = [_chunk("AAPL", 0, "supply chain risk unicorn"), _chunk("AAPL", 1, "currency and demand risk")]
    msft = [_chunk("MSFT", 0, "cloud competition risk")]
    persist_artifact("chunks", "AAPL_10K_2024", aapl, base=base)
    persist_artifact("chunks", "MSFT_10K_2024", msft, base=base)

    def rec(c, vec):
        return {"chunk_id": c.id, "embedding": vec, "metadata": c.metadata()}

    persist_artifact("embeddings", "AAPL_10K_2024", [rec(aapl[0], [1.0, 0.0, 0.0]),
                                                     rec(aapl[1], [0.0, 1.0, 0.0])], base=base)
    persist_artifact("embeddings", "MSFT_10K_2024", [rec(msft[0], [0.0, 0.0, 1.0])], base=base)


def _store(tmp_path):
    return ChromaVectorStore(persist_dir=tmp_path / "vectorstore", collection="test")


def test_upsert_count_and_idempotent(tmp_path):
    _seed(tmp_path)
    store = _store(tmp_path)
    r1 = run_store(base=tmp_path, store=store)
    assert r1 == {"stored": 3, "bm25": 3}
    r2 = run_store(base=tmp_path, store=store)               # re-run
    assert r2["stored"] == 3                                  # upsert by id -> no duplicates


def test_where_query_returns_right_ticker(tmp_path):
    _seed(tmp_path)
    store = _store(tmp_path)
    run_store(base=tmp_path, store=store)
    hits = store.query([1.0, 0.0, 0.0], k=5, where={"ticker": "AAPL"})
    assert len(hits) == 2 and all(h["metadata"]["ticker"] == "AAPL" for h in hits)


def test_bm25_persisted_and_returns_hits(tmp_path):
    _seed(tmp_path)
    run_store(base=tmp_path, store=_store(tmp_path))
    bm = Bm25Index.load(tmp_path / "vectorstore" / "bm25.json")
    hits = bm.query("unicorn", k=3)
    assert hits and hits[0]["id"] == "AAPL_10K_2024_0"       # only the chunk with that term
    assert bm.query("nonexistentterm") == []


def test_bm25_indexes_chunks_without_dense_embeddings(tmp_path):
    _seed(tmp_path)
    persist_artifact("chunks", "TSLA_10K_2024", [_chunk("TSLA", 0, "battery margin catalyst")], base=tmp_path)
    r = run_store(base=tmp_path, store=_store(tmp_path))
    assert r == {"stored": 3, "bm25": 4}
    bm = Bm25Index.load(tmp_path / "vectorstore" / "bm25.json")
    assert bm.query("battery", k=3)[0]["id"] == "TSLA_10K_2024_0"


def test_tokenize():
    assert tokenize("Revenue $391,035 Million!") == ["revenue", "391", "035", "million"]

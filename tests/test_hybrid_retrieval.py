"""Stage 6 tests: dense + sparse retrieval with fakes (no network/Chroma). Filter, hydrate, scores."""

from src.observability import persist_artifact
from src.retrieval import bm25_retriever, vector_retriever
from src.retrieval.metadata_filter import build_filter
from src.retrieval.metadata_parser import parse_query
from src.schemas import Chunk, DocMetadata, HardFilter


def _chunk(cid, ticker="AAPL", year=2024, form="10-K", text="net sales rose", section="Business"):
    return Chunk.from_metadata(
        DocMetadata(company="Apple Inc", ticker=ticker, form=form, filing_date=f"{year}-11-01",
                    source_file=f"{ticker}_{form}_{year}_full.txt", fiscal_period=f"{year}Q4",
                    year=year, quarter="Q4"),
        id=cid, doc_id=f"{ticker}_{form}_{year}", chunk_index=0, section=section, text=text,
    )


def _record(chunk, distance):
    return {"id": chunk.id, "document": chunk.text, "metadata": chunk.metadata(), "distance": distance}


class FakeStore:
    def __init__(self, records):
        self._records = records                       # list of {id,document,metadata,distance}
        self.last_where = "unset"

    def query(self, embedding, k=8, where=None):
        self.last_where = where
        return self._records[:k]

    def get(self, ids):
        by_id = {r["id"]: r for r in self._records}
        return [{"id": i, "document": by_id[i]["document"], "metadata": by_id[i]["metadata"]}
                for i in ids if i in by_id]


class FakeIndex:
    def __init__(self, rows):
        self._rows = rows                             # list of {id,score,metadata}

    def query(self, text, k=8):
        return self._rows[:k]


class FakeEmbedder:
    model = "fake"

    def embed_query(self, text):
        return [0.1, 0.2, 0.3]


def test_vector_search_similarity_and_where():
    c = _chunk("AAPL_10K_2024__Business_c00")
    store = FakeStore([_record(c, distance=0.25)])
    hf = build_filter(parse_query("Apple 2024 10-K"))
    res = vector_retriever.search("apple revenue", hf, embedder=FakeEmbedder(), store=store, k=5)
    assert len(res) == 1
    assert abs(res[0].score - 0.75) < 1e-9            # 1 - distance
    assert res[0].chunk.text == "net sales rose"      # hydrated from Chroma document
    assert store.last_where == hf.where               # hard filter passed through


def test_vector_search_no_filter_passes_none():
    store = FakeStore([_record(_chunk("c0"), 0.1)])
    vector_retriever.search("q", HardFilter(), embedder=FakeEmbedder(), store=store)
    assert store.last_where is None                   # empty filter -> where=None


def test_bm25_filters_by_metadata_and_has_no_text():
    rows = [
        {"id": "AAPL_10K_2024__Business_c00", "score": 3.2, "metadata": _chunk("AAPL_10K_2024__Business_c00").metadata()},
        {"id": "TSLA_10K_2024__Business_c00", "score": 2.1, "metadata": _chunk("TSLA_10K_2024__Business_c00", ticker="TSLA").metadata()},
    ]
    hf = build_filter(parse_query("Apple 10-K"))      # ticker AAPL only
    res = bm25_retriever.search("net sales", hf, index=FakeIndex(rows), k=10)
    assert [r.chunk.ticker for r in res] == ["AAPL"]  # TSLA filtered out
    assert res[0].chunk.text == ""                    # BM25 carries no text yet
    assert res[0].score == 3.2


def test_hydrate_texts_fills_bm25_results_from_store():
    c = _chunk("AAPL_10K_2024__Business_c00", text="the real body text")
    store = FakeStore([_record(c, 0.2)])
    bm = bm25_retriever.search("x", HardFilter(),
                               index=FakeIndex([{"id": c.id, "score": 1.0, "metadata": c.metadata()}]))
    assert bm[0].chunk.text == ""
    hydrated = vector_retriever.hydrate_texts(bm, store)
    assert hydrated[0].chunk.text == "the real body text"


def test_hydrate_texts_falls_back_to_chunk_artifact(tmp_path, monkeypatch):
    c = _chunk("AAPL_10K_2024__Business_c00", text="artifact body text")
    persist_artifact("chunks", "AAPL_10K_2024", [c], base=tmp_path)
    monkeypatch.setattr(vector_retriever, "load_artifact",
                        lambda stage, doc_id: __import__("src.observability", fromlist=["load_artifact"])
                        .load_artifact(stage, doc_id, base=tmp_path))
    bm = bm25_retriever.search("x", HardFilter(),
                               index=FakeIndex([{"id": c.id, "score": 1.0, "metadata": c.metadata()}]))
    hydrated = vector_retriever.hydrate_texts(bm, FakeStore([]))
    assert hydrated[0].chunk.text == "artifact body text"

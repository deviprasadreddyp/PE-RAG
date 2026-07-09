"""EV2 tests: retrieval A/B (hybrid beats single retrievers on pooled recall); scoring shape."""

from src.eval.retrieval_eval import MODES, ab_eval, retrieval_variants, score_variants
from src.schemas import Chunk, DocMetadata


def _chunk(cid, ticker="AAPL", section="Risk Factors"):
    return Chunk.from_metadata(
        DocMetadata(company=f"{ticker} Inc", ticker=ticker, form="10-K", filing_date="2024-11-01",
                    source_file=f"{ticker}_10K_2024_full.txt", year=2024),
        id=cid, doc_id=f"{ticker}_10K_2024", chunk_index=0, section=section, text="body",
    )


def _rec(chunk, distance):
    return {"id": chunk.id, "document": chunk.text, "metadata": chunk.metadata(), "distance": distance}


# Relevant chunks: two distinct AAPL Risk Factors chunks. Vector finds one, BM25 the other.
REL_A = _chunk("AAPL_RF_a", "AAPL", "Risk Factors")
REL_B = _chunk("AAPL_RF_b", "AAPL", "Risk Factors")
IRR_V = _chunk("TSLA_BIZ_v", "TSLA", "Business")
IRR_B = _chunk("MSFT_BIZ_b", "MSFT", "Business")


class FakeStore:
    def __init__(self, recs):
        self._recs = recs

    def query(self, embedding, k=8, where=None):
        return self._recs[:k]

    def get(self, ids):
        by = {r["id"]: r for r in self._recs}
        return [by[i] for i in ids if i in by]


class FakeIndex:
    def __init__(self, rows):
        self._rows = rows

    def query(self, text, k=8):
        return self._rows[:k]


class FakeEmbedder:
    model = "fake"

    def embed_query(self, text):
        return [0.1, 0.2, 0.3]


def _components():
    store = FakeStore([_rec(REL_A, 0.1), _rec(IRR_V, 0.2)])           # vector: REL_A + irrelevant
    index = FakeIndex([{"id": REL_B.id, "score": 3.0, "metadata": REL_B.metadata()},
                       {"id": IRR_B.id, "score": 1.0, "metadata": IRR_B.metadata()}])  # bm25: REL_B + irr
    return {"store": store, "index": index, "embedder": FakeEmbedder(), "reranker": None}


def test_variants_present_and_scored():
    variants = retrieval_variants("Apple risk factors", **_components())
    assert set(variants) == set(MODES)
    scores = score_variants(variants, {"companies": ["AAPL"], "sections": ["Risk Factors"]}, k=8)
    for mode in MODES:
        assert set(scores[mode]) == {"recall@k", "precision@k", "mrr", "ndcg@k"}


def test_hybrid_beats_single_retrievers_on_pooled_recall():
    variants = retrieval_variants("Apple risk factors", **_components())
    s = score_variants(variants, {"companies": ["AAPL"], "sections": ["Risk Factors"]}, k=8)
    # vector found only REL_A, bm25 only REL_B (each 1/2); hybrid finds both (2/2)
    assert s["vector"]["recall@k"] == 0.5
    assert s["bm25"]["recall@k"] == 0.5
    assert s["hybrid"]["recall@k"] == 1.0
    assert s["hybrid"]["recall@k"] >= max(s["vector"]["recall@k"], s["bm25"]["recall@k"])


def test_ab_eval_aggregates_and_skips_refusals():
    cases = [
        {"id": "q1", "question": "Apple risk factors", "companies": ["AAPL"], "sections": ["Risk Factors"]},
        {"id": "q2", "question": "capital of France", "expect_refusal": True},
    ]
    report = ab_eval(cases, **_components())
    assert len(report["per_case"]) == 1                               # refusal case skipped
    assert set(report["summary"]) == set(MODES)
    assert report["summary"]["hybrid"]["recall@k"] == 1.0

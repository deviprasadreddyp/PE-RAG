"""Stage 8 tests: reranking reorders by cross-encoder score; identity fallback; skip-on-fail."""

from src.config import settings
from src.retrieval.reranker import IdentityReranker, get_reranker, rerank
from src.schemas import Chunk, DocMetadata, RetrievalResult


def _rr(cid, text, score=0.0):
    c = Chunk.from_metadata(
        DocMetadata(company="Apple Inc", ticker="AAPL", form="10-K", filing_date="2024-11-01",
                    source_file="AAPL_10K_2024_full.txt"),
        id=cid, doc_id="AAPL_10K_2024", chunk_index=0, section="Business", text=text,
    )
    return RetrievalResult(chunk=c, score=score)


class KeywordReranker:
    """Deterministic fake cross-encoder: score = count of the query word in the chunk text."""

    def rerank(self, query, results, top_k=None):
        top_k = top_k or settings.rerank_top_k
        scored = [(r, float(r.chunk.text.lower().count(query.lower()))) for r in results]
        scored.sort(key=lambda rs: rs[1], reverse=True)
        return [RetrievalResult(chunk=r.chunk, score=s) for r, s in scored[:top_k]]


class BrokenReranker:
    def rerank(self, query, results, top_k=None):
        raise RuntimeError("model blew up")


def test_reranker_reorders_by_relevance():
    results = [_rr("a", "one mention of revenue"), _rr("b", "revenue revenue revenue growth")]
    out = rerank("revenue", results, reranker=KeywordReranker())
    assert out[0].chunk.id == "b"                    # more mentions -> ranked first
    assert out[0].score == 3.0


def test_identity_fallback_keeps_order_and_truncates():
    results = [_rr("a", "x"), _rr("b", "y"), _rr("c", "z")]
    out = IdentityReranker().rerank("q", results, top_k=2)
    assert [r.chunk.id for r in out] == ["a", "b"]


def test_rerank_degrades_to_identity_on_failure():
    results = [_rr("a", "x"), _rr("b", "y")]
    out = rerank("q", results, reranker=BrokenReranker(), top_k=2)
    assert [r.chunk.id for r in out] == ["a", "b"]   # kept RRF order despite the failure


def test_get_reranker_returns_something_usable():
    rr = get_reranker()                              # CrossEncoder if installed, else Identity
    assert hasattr(rr, "rerank")


def test_empty_results():
    assert rerank("q", [], reranker=KeywordReranker()) == []

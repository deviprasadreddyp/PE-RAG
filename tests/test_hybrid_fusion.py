"""Stage 7 tests: RRF formula, cross-list boosting, text preference, ordering, top_n."""

from src.retrieval.hybrid_fusion import reciprocal_rank_fusion
from src.schemas import Chunk, DocMetadata, RetrievalResult


def _rr(cid, score=0.0, text="body"):
    c = Chunk.from_metadata(
        DocMetadata(company="Apple Inc", ticker="AAPL", form="10-K", filing_date="2024-11-01",
                    source_file="AAPL_10K_2024_full.txt"),
        id=cid, doc_id="AAPL_10K_2024", chunk_index=0, section="Business", text=text,
    )
    return RetrievalResult(chunk=c, score=score)


def test_rrf_formula_with_k():
    # single list, ranks 1 and 2, k=1 -> scores 1/2 and 1/3
    fused = reciprocal_rank_fusion([_rr("a"), _rr("b")], k=1)
    by_id = {r.chunk.id: r.score for r in fused}
    assert abs(by_id["a"] - 0.5) < 1e-9
    assert abs(by_id["b"] - (1 / 3)) < 1e-9


def test_item_in_both_lists_ranks_highest():
    vector = [_rr("x"), _rr("a")]      # a at rank 2 here
    bm25 = [_rr("a"), _rr("y")]        # a at rank 1 here
    fused = reciprocal_rank_fusion(vector, bm25, k=60)
    assert fused[0].chunk.id == "a"    # appears in both -> highest fused score


def test_prefers_text_bearing_copy():
    bm25 = [_rr("a", text="")]         # BM25 copy: no text
    vector = [_rr("a", text="real body")]
    fused = reciprocal_rank_fusion(bm25, vector, k=60)
    assert len(fused) == 1 and fused[0].chunk.text == "real body"


def test_ordering_descending_and_top_n():
    fused = reciprocal_rank_fusion([_rr("a"), _rr("b"), _rr("c")], k=10, top_n=2)
    assert [r.chunk.id for r in fused] == ["a", "b"]
    assert fused[0].score >= fused[1].score


def test_single_list_passthrough_order():
    fused = reciprocal_rank_fusion([_rr("a"), _rr("b"), _rr("c")], k=60)
    assert [r.chunk.id for r in fused] == ["a", "b", "c"]

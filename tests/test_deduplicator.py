"""Stage 9 tests: exact-content dedupe, per-section cap, order preservation, cross-section diversity."""

import hashlib

from src.retrieval.deduplicator import deduplicate
from src.schemas import Chunk, DocMetadata, RetrievalResult


def _rr(cid, text, doc="AAPL_10K_2024", section="Business", score=0.0):
    c = Chunk.from_metadata(
        DocMetadata(company="Apple Inc", ticker="AAPL", form="10-K", filing_date="2024-11-01",
                    source_file="AAPL_10K_2024_full.txt"),
        id=cid, doc_id=doc, chunk_index=0, section=section, text=text,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
    )
    return RetrievalResult(chunk=c, score=score)


def test_exact_content_duplicate_removed():
    out = deduplicate([_rr("a", "same body"), _rr("b", "same body")])
    assert [r.chunk.id for r in out] == ["a"]          # identical text -> second dropped


def test_per_section_cap():
    rs = [_rr(f"c{i}", f"body {i}", section="Risk Factors") for i in range(5)]
    out = deduplicate(rs, max_per_section=3)
    assert len(out) == 3                               # capped at 3 from one section


def test_cross_section_diversity_kept():
    rs = [_rr("a", "b1", section="Business"),
          _rr("b", "b2", section="Risk Factors"),
          _rr("c", "b3", section="Management's Discussion and Analysis")]
    out = deduplicate(rs, max_per_section=1)
    assert [r.chunk.section for r in out] == ["Business", "Risk Factors", "Management's Discussion and Analysis"]


def test_order_preserved():
    rs = [_rr("a", "x"), _rr("b", "y"), _rr("c", "z")]
    assert [r.chunk.id for r in deduplicate(rs)] == ["a", "b", "c"]


def test_same_id_deduped():
    out = deduplicate([_rr("a", "one"), _rr("a", "two")])   # same id, different text
    assert [r.chunk.id for r in out] == ["a"]

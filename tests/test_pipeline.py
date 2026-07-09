"""Orchestrator tests: full pipeline with fakes (no network/keys) — happy path, refusals, trace."""

from src.generation.generate import generate  # noqa: F401  (ensures module import path is valid)
from src.retrieval.retrieval_pipeline import answer_query
from src.schemas import AnswerBody, Chunk, DocMetadata


def _chunk(cid, ticker="AAPL", year=2024, section="Risk Factors", text="supply-chain risk exposure"):
    return Chunk.from_metadata(
        DocMetadata(company=f"{ticker} Inc", ticker=ticker, form="10-K", filing_date=f"{year}-11-01",
                    source_file=f"{ticker}_10K_{year}_full.txt", year=year, fiscal_period=f"{year}Q4",
                    source_url=f"https://sec.gov/{ticker}"),
        id=cid, doc_id=f"{ticker}_10K_{year}", chunk_index=0, section=section, text=text,
    )


def _record(chunk, distance):
    return {"id": chunk.id, "document": chunk.text, "metadata": chunk.metadata(), "distance": distance}


class FakeStore:
    def __init__(self, records):
        self._records = records

    def query(self, embedding, k=8, where=None):
        return self._records[:k]

    def get(self, ids):
        by = {r["id"]: r for r in self._records}
        return [{"id": i, "document": by[i]["document"], "metadata": by[i]["metadata"]}
                for i in ids if i in by]


class FakeIndex:
    def __init__(self, rows):
        self._rows = rows

    def query(self, text, k=8):
        return self._rows[:k]


class FakeEmbedder:
    model = "fake"

    def embed_query(self, text):
        return [0.1, 0.2, 0.3]


class FakeGenerator:
    def __init__(self):
        self.calls = 0

    def generate(self, prompt):
        self.calls += 1
        return AnswerBody(executive_summary="Apple faces supply-chain risk [E1].",
                          supporting_evidence="Risk exposure noted [E1].", citations=["E1"],
                          confidence="High")


def _store_index(chunks, distance=0.1):
    recs = [_record(c, distance) for c in chunks]
    rows = [{"id": c.id, "score": 2.0, "metadata": c.metadata()} for c in chunks]
    return FakeStore(recs), FakeIndex(rows)


def test_happy_path_answers_with_citations_one_call():
    store, index = _store_index([_chunk("AAPL_10K_2024__RiskFactors_c00")], distance=0.1)  # sim 0.9
    gen = FakeGenerator()
    res = answer_query("What are Apple's risk factors?", store=store, index=index,
                       embedder=FakeEmbedder(), generator=gen)
    assert not res.refused
    assert gen.calls == 1                                    # exactly one LLM call
    assert res.answer.sources and res.answer.sources[0].ticker == "AAPL"
    assert res.guardrail.confidence == "High"
    assert res.trace["evidence_ids"] == ["AAPL_10K_2024__RiskFactors_c00"]


def test_low_similarity_refuses_without_llm():
    store, index = _store_index([_chunk("AAPL_10K_2024__RiskFactors_c00")], distance=0.8)  # sim 0.2
    gen = FakeGenerator()
    res = answer_query("Apple risk factors", store=store, index=index,
                       embedder=FakeEmbedder(), generator=gen)
    assert res.refused and gen.calls == 0                    # zero LLM calls on refusal
    assert "Information unavailable" in res.answer.answer


def test_invalid_query_refuses_without_llm():
    gen = FakeGenerator()
    res = answer_query("  ", generator=gen)
    assert res.refused and gen.calls == 0


def test_missing_company_coverage_refuses():
    # ask to compare Apple & Tesla but only AAPL is retrievable
    store, index = _store_index([_chunk("AAPL_10K_2024__RiskFactors_c00", "AAPL")], distance=0.1)
    gen = FakeGenerator()
    res = answer_query("Compare Apple and Tesla risk factors", store=store, index=index,
                       embedder=FakeEmbedder(), generator=gen)
    assert res.refused and gen.calls == 0
    assert "TSLA" in res.answer.answer


def test_bm25_only_when_vector_unavailable():
    # no embedder/store -> vector skipped; BM25 still returns; answers with Low confidence
    chunks = [_chunk("AAPL_10K_2024__RiskFactors_c00")]
    _, index = _store_index(chunks)
    store = FakeStore([_record(chunks[0], 0.1)])             # store present for hydration
    gen = FakeGenerator()
    res = answer_query("Apple risk factors", store=store, index=index, embedder=None, generator=gen)
    assert not res.refused and gen.calls == 1
    assert res.trace["vector_ids"] == [] and res.trace["bm25_ids"]


def test_trace_is_populated():
    store, index = _store_index([_chunk("AAPL_10K_2024__RiskFactors_c00")])
    res = answer_query("Apple risk factors", store=store, index=index,
                       embedder=FakeEmbedder(), generator=FakeGenerator())
    for key in ("query", "intents", "filter", "plan", "vector_ids", "rrf_ids", "evidence_ids", "guardrail"):
        assert key in res.trace

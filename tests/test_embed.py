"""Stage 7 tests: MOCK the embedder (no network). Batching, caching, embeds embed_text, record shape."""

from src.observability import load_artifact, persist_artifact
from src.pipeline.embed import EmbeddingCache, cache_key, embed_texts, run_embed
from src.schemas import Chunk, DocMetadata, EmbeddingRecord


class FakeEmbedder:
    """Deterministic, network-free embedder that records the batches it was asked to embed."""

    model = "fake-embed"

    def __init__(self):
        self.calls: list[list[str]] = []

    def embed_documents(self, texts):
        self.calls.append(list(texts))
        return [[float(len(t)), float(sum(map(ord, t)) % 100)] for t in texts]

    def embed_query(self, text):
        return [float(len(text)), float(sum(map(ord, text)) % 100)]


def _chunk(i: int, embed_text: str, text: str = "orig") -> Chunk:
    return Chunk.from_metadata(
        DocMetadata(company="Apple Inc", ticker="AAPL", form="10-K", filing_date="2022-10-28",
                    source_file="AAPL_10K_2024_full.txt", fiscal_period="2022Q3", year=2022),
        id=f"AAPL_10K_2024_{i}", doc_id="AAPL_10K_2024", chunk_index=i,
        section="Risk Factors", text=text, embed_text=embed_text,
    )


def _persist_chunks(chunks, base):
    persist_artifact("chunks", "AAPL_10K_2024", chunks, base=base)


def test_embeds_embed_text_not_text_in_one_batch(tmp_path):
    chunks = [_chunk(0, "ENRICHED A", "orig A"), _chunk(1, "ENRICHED B", "orig B")]
    _persist_chunks(chunks, tmp_path)
    fake = FakeEmbedder()
    run_embed("AAPL_10K_2024", embedder=fake, base=tmp_path)
    assert fake.calls == [["ENRICHED A", "ENRICHED B"]]          # embed_text, single batch of misses


def test_cache_hit_on_second_run(tmp_path):
    _persist_chunks([_chunk(0, "ENRICHED A"), _chunk(1, "ENRICHED B")], tmp_path)
    run_embed("AAPL_10K_2024", embedder=FakeEmbedder(), base=tmp_path)  # populate cache
    fake2 = FakeEmbedder()
    run_embed("AAPL_10K_2024", embedder=fake2, base=tmp_path)           # all cached
    assert fake2.calls == []                                    # nothing re-embedded


def test_only_new_chunks_embedded_on_partial_change(tmp_path):
    _persist_chunks([_chunk(0, "ENRICHED A"), _chunk(1, "ENRICHED B")], tmp_path)
    run_embed("AAPL_10K_2024", embedder=FakeEmbedder(), base=tmp_path)
    _persist_chunks([_chunk(0, "ENRICHED A"), _chunk(1, "ENRICHED B"), _chunk(2, "ENRICHED C")], tmp_path)
    fake = FakeEmbedder()
    run_embed("AAPL_10K_2024", embedder=fake, base=tmp_path)
    assert fake.calls == [["ENRICHED C"]]                        # only the new one


def test_persisted_record_shape_and_metadata(tmp_path):
    _persist_chunks([_chunk(0, "ENRICHED A")], tmp_path)
    rep = run_embed("AAPL_10K_2024", embedder=FakeEmbedder(), base=tmp_path)
    recs = load_artifact("embeddings", "AAPL_10K_2024", base=tmp_path)
    assert rep == {"doc_id": "AAPL_10K_2024", "count": 1, "dim": 2}
    r0 = recs[0]
    assert set(r0) == {"chunk_id", "embedding", "metadata"}
    assert EmbeddingRecord.model_validate(r0)                     # persisted as a typed record
    assert r0["chunk_id"] == "AAPL_10K_2024_0"
    assert r0["metadata"]["ticker"] == "AAPL" and "text" not in r0["metadata"]
    assert len(r0["embedding"]) == 2


def test_cache_key_is_deterministic_and_model_scoped():
    assert cache_key("m1", "x") == cache_key("m1", "x")
    assert cache_key("m1", "x") != cache_key("m2", "x")          # model change -> different key


def test_embed_texts_uses_cache_directly(tmp_path):
    cache = EmbeddingCache(base=tmp_path)
    fake = FakeEmbedder()
    v1 = embed_texts(["hello", "world"], fake, cache)
    v2 = embed_texts(["hello", "world"], fake, cache)            # second call: all cached
    assert v1 == v2 and len(fake.calls) == 1

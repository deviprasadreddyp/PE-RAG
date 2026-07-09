"""Config tests: defaults, env loading, overrides, validation, and secret handling."""

from pathlib import Path

import pytest

from src.config import Settings

_ENVS = (
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "VOYAGE_API_KEY",
    "CHUNK_MAX_CHARS", "CHUNK_OVERLAP", "EMBEDDING_MODEL", "GENERATION_MODEL",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ambient env vars must not leak into the assertions below."""
    for k in _ENVS:
        monkeypatch.delenv(k, raising=False)


def _mk(**kw) -> Settings:
    # _env_file=None: never read a real .env during tests (deterministic)
    return Settings(_env_file=None, **kw)


def test_defaults():
    s = _mk()
    assert s.embedding_model == "BAAI/bge-large-en-v1.5"
    assert s.generation_model == "claude-opus-4-8"
    assert s.chunk_max_chars > s.chunk_overlap >= 0
    assert s.data_dir == "data"
    assert s.corpus_dir == "edgar_corpus"


def test_collection_name_includes_embedding_model():
    s = _mk()
    assert s.collection_base in s.collection_name
    assert "bge-large-en-v1.5" in s.collection_name          # "/" sanitized: BAAI-bge-large-en-v1.5


def test_env_loading(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    monkeypatch.setenv("CHUNK_MAX_CHARS", "800")
    s = _mk()
    assert s.openai_api_key.get_secret_value() == "sk-openai-test"
    assert s.chunk_max_chars == 800


def test_kwarg_override():
    s = _mk(chunk_max_chars=800, chunk_overlap=20)
    assert (s.chunk_max_chars, s.chunk_overlap) == (800, 20)


def test_overlap_must_be_less_than_size():
    with pytest.raises(ValueError):
        _mk(chunk_max_chars=700, chunk_overlap=700)


def test_retrieval_defaults():
    s = _mk()
    assert (s.vector_top_k, s.bm25_top_k, s.rrf_k) == (20, 20, 60)
    assert s.rerank_top_k == 8 and s.candidate_pool == 30
    assert s.min_similarity == 0.35
    assert s.rerank_model == "BAAI/bge-reranker-base"
    assert (s.min_query_chars, s.max_query_chars) == (3, 1000)


def test_retrieval_field_bounds_enforced():
    with pytest.raises(ValueError):
        _mk(rerank_top_k=999)              # above le=20
    with pytest.raises(ValueError):
        _mk(min_similarity=2.0)            # above le=1.0
    with pytest.raises(ValueError):
        _mk(vector_top_k=1)               # below ge=5


def test_secret_not_exposed_in_repr():
    s = _mk(openai_api_key="sk-should-stay-hidden")
    assert "sk-should-stay-hidden" not in repr(s)


def test_require_key_guards():
    with pytest.raises(RuntimeError):
        _mk().require_openai_key()
    assert _mk(openai_api_key="sk-x").require_openai_key() == "sk-x"


def test_embedding_policy_defaults(monkeypatch):
    monkeypatch.delenv("EMBED_BATCH_SIZE", raising=False)
    monkeypatch.delenv("EMBED_MAX_RETRIES", raising=False)
    s = _mk()
    assert s.embed_batch_size == 100 and s.embed_max_retries == 3
    monkeypatch.setenv("EMBED_BATCH_SIZE", "256")
    assert _mk().embed_batch_size == 256


def test_paths():
    s = _mk()
    assert s.data_path == Path("data")
    assert s.chroma_path == Path("data/vectorstore")
    assert s.embedding_cache_dir == Path("data/.embedding_cache")

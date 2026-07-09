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
    assert s.embedding_model == "text-embedding-3-large"
    assert s.generation_model == "claude-opus-4-8"
    assert s.chunk_max_chars > s.chunk_overlap >= 0
    assert s.data_dir == "data"
    assert s.corpus_dir == "edgar_corpus"


def test_collection_name_includes_embedding_model():
    s = _mk()
    assert s.collection_base in s.collection_name
    assert "text-embedding-3-large" in s.collection_name


def test_env_loading(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    monkeypatch.setenv("CHUNK_MAX_CHARS", "512")
    s = _mk()
    assert s.openai_api_key.get_secret_value() == "sk-openai-test"
    assert s.chunk_max_chars == 512


def test_kwarg_override():
    s = _mk(chunk_max_chars=200, chunk_overlap=20)
    assert (s.chunk_max_chars, s.chunk_overlap) == (200, 20)


def test_overlap_must_be_less_than_size():
    with pytest.raises(ValueError):
        _mk(chunk_max_chars=100, chunk_overlap=100)


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

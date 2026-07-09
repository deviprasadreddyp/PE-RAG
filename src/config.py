"""Typed settings for PE-RAG, loaded from the environment / ``.env``.

Single source of truth for model IDs, chunking params, and paths. Secrets are
``SecretStr`` so they never leak into logs or reprs, and they are validated only
at point of use (``require_*``) — importing this module never fails just because
a key is unset, so the deterministic stages that need no key still run.

Usage::

    from src.config import settings
    settings.embedding_model            # "text-embedding-3-large"
    settings.require_openai_key()       # raises if OPENAI_API_KEY is unset
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Field ``x`` is read from env var ``X`` (case-insensitive)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Secrets (empty until provided; validated at point of use) ---
    openai_api_key: SecretStr = SecretStr("")       # embeddings: text-embedding-3-large
    anthropic_api_key: SecretStr = SecretStr("")    # the single answer-generation call (Phase 2)

    # --- Models ---
    embedding_model: str = "text-embedding-3-large"
    generation_model: str = "claude-opus-4-8"

    # --- Chunking: Section-Aware Hierarchical Chunking (see architecture/CHUNKING_STRATEGY.md) ---
    # Sections are the semantic unit (the parents). WITHIN each section the recursive splitter
    # packs boundary-preserving pieces UP TO a MAXIMUM size — this is a ceiling, NOT a fixed
    # target: short sections stay whole (one small chunk); long ones split only at real
    # boundaries. Char-based (~750 tokens; filings have ~no blank-line paragraphs). Tuned by eval.
    chunk_max_chars: int = Field(3000, ge=600, le=6000)     # per-chunk MAX cap, not a fixed size
    chunk_overlap: int = Field(300, ge=0, le=1000)

    # --- Retrieval (Phase 2; see architecture/RETRIEVAL_DESIGN.md §7) ---
    vector_top_k: int = Field(20, ge=5, le=100)          # dense recall pool before fusion
    bm25_top_k: int = Field(20, ge=5, le=100)            # lexical recall pool before fusion
    rrf_k: int = Field(60, ge=1, le=1000)                # Reciprocal Rank Fusion constant
    candidate_pool: int = Field(30, ge=5, le=200)        # fused pool handed to the reranker
    rerank_top_k: int = Field(8, ge=1, le=20)            # final evidence count into the prompt
    rerank_model: str = "BAAI/bge-reranker-base"         # local cross-encoder ("-large" if latency allows)
    min_similarity: float = Field(0.35, ge=0.0, le=1.0)  # below this a candidate is treated as non-evidence
    max_query_chars: int = Field(1000, ge=50, le=4000)   # reject pathological queries
    min_query_chars: int = Field(3, ge=1, le=50)         # reject empty / one-char queries

    # --- Embedding request policy (explicit; not left to SDK defaults) ---
    embed_batch_size: int = Field(100, ge=1, le=2048)    # chunks per OpenAI embeddings request
    embed_max_retries: int = Field(3, ge=0, le=10)       # retries w/ exponential backoff on 429/5xx

    # --- Paths ---
    data_dir: str = "data"
    corpus_dir: str = "edgar_corpus"
    chroma_dir: str = "data/vectorstore"
    collection_base: str = "sec_filings"

    # --- Validation ---
    @model_validator(mode="after")
    def _overlap_lt_size(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_max_chars:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be < chunk_max_chars "
                f"({self.chunk_max_chars})"
            )
        return self

    # --- Derived values ---
    @property
    def collection_name(self) -> str:
        """Chroma collection, namespaced by embedding model so a model change ⇒ a fresh index."""
        safe = re.sub(r"[^A-Za-z0-9_.-]", "-", self.embedding_model)
        return f"{self.collection_base}__{safe}"

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def corpus_path(self) -> Path:
        return Path(self.corpus_dir)

    @property
    def chroma_path(self) -> Path:
        return Path(self.chroma_dir)

    @property
    def embedding_cache_dir(self) -> Path:
        return self.data_path / ".embedding_cache"

    # --- Secret guards (fail loudly, only when actually needed) ---
    def require_openai_key(self) -> str:
        v = self.openai_api_key.get_secret_value()
        if not v:
            raise RuntimeError("OPENAI_API_KEY is not set (needed for embeddings). Add it to .env.")
        return v

    def require_anthropic_key(self) -> str:
        v = self.anthropic_api_key.get_secret_value()
        if not v:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set (needed for the answer call). Add it to .env."
            )
        return v


# Import-time singleton used across the codebase.
settings = Settings()

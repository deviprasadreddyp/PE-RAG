"""PE-RAG — an observable ingestion & retrieval pipeline over SEC filings.

Deterministic, stage-based design: each offline stage reads the previous stage's
artifact and persists its own under ``data/<stage>/`` so every step is
inspectable. The only non-deterministic step is the single Claude generation
call (Phase 2). See ``agents.md`` and ``architecture/HLD.md``.
"""

__version__ = "0.1.0"

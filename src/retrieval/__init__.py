"""Phase 2 — query-time retrieval & generation.

Everything in this package is **deterministic or local ML**; the only generative step is the
single Claude call in ``src/generation/generate.py``. See ``architecture/RETRIEVAL_DESIGN.md``.

Stages: validate -> classify -> extract metadata -> build hard filter -> plan -> hybrid search
-> RRF -> rerank -> dedup -> evidence -> guardrails -> prompt -> [ONE LLM CALL] -> parse -> cite.
"""


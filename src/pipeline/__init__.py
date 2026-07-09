"""Offline ingestion & indexing stages (HLD Stages 1-8).

ingest -> clean -> metadata -> sections -> chunk -> enrich -> embed -> store.
Each stage persists an inspectable artifact to ``data/<stage>/``. Deterministic;
no LLM in this phase.
"""

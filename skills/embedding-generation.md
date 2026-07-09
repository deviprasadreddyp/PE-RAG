# Skill: embedding-generation

**Purpose.** Turn chunks and queries into vectors: which model, how to batch, how to cache, and how
to keep query and document embeddings consistent.

**When to invoke.** Work in `sec_rag/index/embedder.py`; any embedding call.

## How to do it
1. **Model.** Default to Voyage **`voyage-finance-2`** (finance-domain, 1024-dim) — the corpus is
   financial filings. Fallback: local `BAAI/bge-small-en-v1.5` via `sentence-transformers` when no
   `VOYAGE_API_KEY` (offline demo). Both sit behind one `Embedder` protocol so the store never knows
   which is used.
2. **Consistency.** Embed the corpus and the query with the **same model + version**. Voyage uses
   `input_type="document"` for chunks and `input_type="query"` for queries — set it correctly; never
   mix models between index and query time (a re-index is required if the model changes).
3. **Batch.** Embed in batches (e.g. 128 texts/call), not one call per chunk — this dominates ingest
   cost and time. Bulk-upsert to the store.
4. **Cache.** Cache each embedding by `sha256(model + text)` in `data/embedding_cache/`. Re-running
   `build_index.py` must not re-embed unchanged chunks (`cost-optimizer` + non-negotiable idempotency).
5. **Normalize** for cosine similarity; make sure the store's distance metric matches (cosine).

## Bad example
```python
# BAD: one API call per chunk, no cache, query embedded with a different model
vecs = [openai_embed(c.text) for c in chunks]      # N calls, re-embeds every run, wrong domain model
qvec = bge_embed(query)                             # query model ≠ document model → garbage similarity
```

## Good example
```python
class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...

class VoyageEmbedder:
    MODEL = "voyage-finance-2"
    def embed_documents(self, texts):
        out, todo, idx = [None]*len(texts), [], []
        for i, t in enumerate(texts):
            hit = cache_get(self.MODEL, t)
            if hit is None: todo.append(t); idx.append(i)
            else: out[i] = hit
        for batch, positions in batched(todo, idx, size=128):
            for pos, vec in zip(positions, voyage.embed(batch, model=self.MODEL,
                                                         input_type="document").embeddings):
                out[pos] = vec; cache_put(self.MODEL, texts[pos], vec)
        return out
    def embed_query(self, text):
        return voyage.embed([text], model=self.MODEL, input_type="query").embeddings[0]
```

## Failure modes seen
- Embedding query and documents with different models/versions → silently poor retrieval.
- One call per chunk → slow, expensive ingest that times out on the full corpus.
- No cache → every `build_index.py` run re-pays the full embedding cost.
- Distance metric mismatch (dot vs cosine) between embedder output and store config.
- Forgetting `input_type` on Voyage → measurably worse retrieval.

## MUST NOT
- MUST NOT mix embedding models/versions between index time and query time.
- MUST NOT hardcode the API key — read `VOYAGE_API_KEY` from env.
- MUST NOT re-embed unchanged content on re-index (cache by content hash).
- MUST NOT couple retrieval code to a concrete embedder — depend on the `Embedder` protocol.

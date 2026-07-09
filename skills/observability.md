# Skill: observability

**Purpose.** The core pattern of this project: **every offline stage persists its output to
`data/<stage>/` so it can be inspected.** Nothing is a black box. This is what turns "a RAG" into an
*observable pipeline* — and it's what the evaluator is looking for.

**When to invoke.** Every stage in `src/pipeline/` and `src/retrieval/`. Use the shared helpers in
`src/observability.py`; do not hand-roll file I/O per stage.

## How to do it
1. **One artifact per stage, per input.** Each stage reads the previous stage's artifact and writes
   its own, named after the source filing:
   `data/raw/AAPL_10K_2024.txt` → `data/cleaned/AAPL_10K_2024.txt` → `data/metadata/AAPL_10K_2024.json`
   → `data/sections/AAPL_10K_2024.json` → `data/chunks/AAPL_10K_2024.json` →
   `data/embeddings/AAPL_10K_2024.json` → `data/vectorstore/`.
2. **Format by content.** Raw/cleaned = `.txt`; structured stages = pretty-printed `.json`
   (`indent=2`, `ensure_ascii=False`) so a human can open and read them.
3. **Shared helpers.** `persist_artifact(stage, doc_id, obj)` and `load_artifact(stage, doc_id)` in
   `src/observability.py`. Every stage calls them — consistent paths, consistent format.
4. **Stages are runnable in isolation.** Each has a `scripts/run_<stage>.py` so you can run just that
   stage and inspect its `data/<stage>/` output without running the whole pipeline.
5. **Idempotent.** Re-running a stage overwrites its artifact deterministically (same input ⇒ same
   output). No timestamps in the artifact body.

## Bad example
```python
# BAD: stages chained in memory, nothing persisted — a black box
raw = load_all(); cleaned = clean(raw); chunks = chunk(cleaned); embed_and_store(chunks)
# If chunking dropped a table or metadata is wrong, you cannot see WHERE — only the final answer.
```

## Good example
```python
# src/observability.py
import json, pathlib
DATA = pathlib.Path("data")
def persist_artifact(stage: str, doc_id: str, obj, ext="json"):
    p = DATA / stage / f"{doc_id}.{ext}"; p.parent.mkdir(parents=True, exist_ok=True)
    if ext == "json": p.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    else: p.write_text(obj, encoding="utf-8")
    return p
def load_artifact(stage: str, doc_id: str, ext="json"):
    p = DATA / stage / f"{doc_id}.{ext}"
    return json.loads(p.read_text("utf-8")) if ext == "json" else p.read_text("utf-8")

# every stage follows this shape:
def run_clean(doc_id):
    raw = load_artifact("raw", doc_id, ext="txt")
    cleaned = clean(raw)                              # deterministic
    persist_artifact("cleaned", doc_id, cleaned, ext="txt")   # inspectable
```

## Failure modes seen
- Chaining stages in memory with no persistence → can't localize a failure; the whole thing is opaque.
- Each stage inventing its own paths/formats → inconsistent, un-inspectable `data/`.
- Non-deterministic artifacts (timestamps/UUIDs in the body) → diffs are noise; re-runs look "changed."
- Persisting only the final index → the "observable pipeline" story collapses.

## MUST NOT
- MUST NOT chain stages without persisting each stage's artifact to `data/<stage>/`.
- MUST NOT bypass `persist_artifact`/`load_artifact` with ad-hoc I/O.
- MUST NOT put wall-clock/random values in a stage artifact body (breaks determinism/idempotency).
- MUST NOT write into `data/` from the front-end request path (read persisted artifacts, don't rebuild).

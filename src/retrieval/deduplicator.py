"""Stage 9 — deduplication (deterministic; no LLM).

Remove redundant evidence so the prompt carries diverse, non-repetitive context:
- **Exact duplicates** — same ``content_hash`` (identical text, e.g. boilerplate repeated across
  filings) or the same chunk id.
- **Section flooding** — cap how many chunks may come from one (doc, section) so a single section's
  adjacent chunks (Chunk 4, 5, 6 of the same paragraph) don't crowd out other evidence.

Input order (already rerank-ranked, best-first) is preserved.
"""

from __future__ import annotations

from src.schemas import RetrievalResult

DEFAULT_MAX_PER_SECTION = 3


def deduplicate(results: list[RetrievalResult], *, max_per_section: int = DEFAULT_MAX_PER_SECTION
                ) -> list[RetrievalResult]:
    """Drop exact duplicates and cap chunks per (doc, section); keep best-first order."""
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    per_section: dict[tuple[str, str], int] = {}
    out: list[RetrievalResult] = []
    for r in results:
        c = r.chunk
        if c.id in seen_ids:
            continue
        h = c.content_hash or c.text                      # fall back to text if no hash
        if h in seen_hashes:
            continue
        key = (c.doc_id, c.section)
        if per_section.get(key, 0) >= max_per_section:
            continue
        out.append(r)
        seen_ids.add(c.id)
        seen_hashes.add(h)
        per_section[key] = per_section.get(key, 0) + 1
    return out

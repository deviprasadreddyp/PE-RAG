"""Stage 5 — chunk generation: Section-Aware Hierarchical Chunking.

Strategy (see architecture/CHUNKING_STRATEGY.md): the filing's detected sections
(Stage 4) are the semantic hierarchy — the *parents*. We split each section
independently into retrieval-sized *child* chunks with LangChain's
``RecursiveCharacterTextSplitter`` (a boundary-preserving splitter: paragraph ->
line -> sentence -> word, hard-splitting only as a last resort). Chunks therefore
never span two sections. Each ``Chunk`` records its place in the hierarchy
(``section_index`` = which parent, ``section_chunk_index`` = position within it,
``chunk_index`` = global order), a stable **section-aware** id
``"{doc_id}__{SectionSlug}_c{NN}"`` (e.g. `AAPL_10K_2022Q3_2022-10-28__RiskFactors_c03`), and the full
filing metadata (``embed_text`` is filled in Stage 6). Persist to
``data/chunks/<doc_id>.json``. Deterministic; no LLM.

Run standalone:  python -m src.pipeline.chunk
"""

from __future__ import annotations

import hashlib
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import settings
from src.observability import list_artifacts, load_artifact, persist_artifact, run_docs
from src.pipeline.section_resolution import apply_section_resolution
from src.schemas import Chunk, DocMetadata, SectionSpan

SEPARATORS = ["\n\n", "\n", ". ", " ", ""]   # real boundaries first; "" hard-splits as last resort
_WORD = re.compile(r"[A-Za-z0-9]+")
_MONEY_OR_NUMBER = re.compile(r"(?:\$|\b\d[\d,]*(?:\.\d+)?\b)")
_PAGE_FOOTER = re.compile(r"\bForm\s+10-[KQ]\s*\|\s*\d+\s*$", re.I)
TABLE_CONTEXT_CHARS = 280


def _slug(section_name: str) -> str:
    """'Risk Factors' -> 'RiskFactors' (CamelCase, alnum only, capped)."""
    s = "".join(w[:1].upper() + w[1:] for w in _WORD.findall(section_name))[:30]
    return s or "Section"


def make_splitter(chunk_size: int | None = None, chunk_overlap: int | None = None):
    # LangChain's chunk_size IS a maximum: it packs pieces up to the cap, so small
    # sections yield one short chunk and only long sections split. Default = settings cap.
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_max_chars if chunk_size is None else chunk_size,
        chunk_overlap=settings.chunk_overlap if chunk_overlap is None else chunk_overlap,
        separators=SEPARATORS,
        keep_separator=True,
        length_function=len,
    )


def _chunk_cap(splitter) -> int:
    """Best-effort access to LangChain's configured max chunk size."""
    return int(getattr(splitter, "_chunk_size", settings.chunk_max_chars))


def _is_table_line(line: str) -> bool:
    """Heuristic for SEC table rows/aligned financial statement lines."""
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.count("|") >= 2:
        return True
    numeric_cells = len(_MONEY_OR_NUMBER.findall(stripped))
    has_columns = len(re.findall(r"\S {2,}\S", stripped)) >= 2
    return numeric_cells >= 3 and has_columns


def _split_table_block(block: str, *, max_chars: int, splitter) -> list[str]:
    """Pack a table-like block on line boundaries; never cut a row mid-line."""
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    rows = [r.rstrip() for r in block.splitlines() if r.strip()]

    def header_rows() -> list[str]:
        heads: list[str] = []
        for row in rows[:3]:
            numeric = len(_MONEY_OR_NUMBER.findall(row))
            looks_like_period_header = bool(
                re.search(r"\b(?:19|20)\d{2}\b|three months|six months|year(?:s)? ended|change", row, re.I)
            )
            if numeric == 0 or looks_like_period_header:
                heads.append(row)
                continue
            break
        return heads[:2]

    headers = header_rows()

    def emit(part_rows: list[str]) -> None:
        if not part_rows:
            return
        rows_out = list(part_rows)
        if headers and rows_out[:len(headers)] != headers:
            candidate = headers + rows_out
            if len("\n".join(candidate)) <= max_chars + TABLE_CONTEXT_CHARS:
                rows_out = candidate
        chunks.append("\n".join(rows_out).strip())

    for row in rows:
        if len(row) > max_chars:
            if cur:
                emit(cur)
                cur, cur_len = [], 0
            chunks.extend(p.strip() for p in splitter.split_text(row) if p.strip())
            continue
        add_len = len(row) + (1 if cur else 0)
        if cur and cur_len + add_len > max_chars:
            emit(cur)
            cur, cur_len = [], 0
        cur.append(row)
        cur_len += add_len
    if cur:
        emit(cur)
    return chunks


def _table_context(block: str) -> str:
    """Carry a nearby caption/units line into table chunks without inventing text."""
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    kept: list[str] = []
    for line in reversed(lines[-5:]):
        if _is_table_line(line) or _PAGE_FOOTER.search(line):
            continue
        if len(line) > TABLE_CONTEXT_CHARS:
            line = line[-TABLE_CONTEXT_CHARS:].strip()
        kept.append(line)
        if sum(len(x) for x in kept) >= TABLE_CONTEXT_CHARS or len(kept) >= 2:
            break
    return "\n".join(reversed(kept)).strip()


def _prepend_table_context(context: str, table_chunk: str, *, max_chars: int) -> str:
    if not context or context in table_chunk:
        return table_chunk
    candidate = f"{context}\n{table_chunk}"
    return candidate if len(candidate) <= max_chars + TABLE_CONTEXT_CHARS else table_chunk


def split_section_text(section_text: str, splitter=None) -> list[str]:
    """Split one section, preserving table-like line blocks on row boundaries."""
    splitter = splitter or make_splitter()
    max_chars = _chunk_cap(splitter)
    lines = section_text.splitlines()
    if not lines:
        return [p.strip() for p in splitter.split_text(section_text) if p.strip()]

    blocks: list[tuple[bool, str]] = []
    cur: list[str] = []
    cur_table: bool | None = None
    for line in lines:
        is_table = _is_table_line(line)
        if cur and is_table != cur_table:
            blocks.append((bool(cur_table), "\n".join(cur)))
            cur = []
        cur.append(line)
        cur_table = is_table
    if cur:
        blocks.append((bool(cur_table), "\n".join(cur)))

    out: list[str] = []
    context = ""
    for is_table, block in blocks:
        if is_table:
            out.extend(
                _prepend_table_context(context, p, max_chars=max_chars)
                for p in _split_table_block(block, max_chars=max_chars, splitter=splitter)
            )
        else:
            parts = [p.strip() for p in splitter.split_text(block) if p.strip()]
            out.extend(parts)
            tail = _table_context(block)
            if tail:
                context = tail
    return [p for p in out if p]


def chunk_document(
    doc_id: str, meta: DocMetadata, cleaned: str, sections: list[SectionSpan], *, splitter=None
) -> list[Chunk]:
    """Split each section independently into Chunks with a global running index."""
    splitter = splitter or make_splitter()
    out: list[Chunk] = []
    used: set[str] = set()
    idx = 0
    for section_index, span in enumerate(sections):          # parent nodes
        slug = _slug(span.section_name)
        section_chunk_index = 0
        for piece in split_section_text(cleaned[span.start:span.end], splitter=splitter):
            piece = piece.strip()
            if not piece:
                continue
            # section-aware, deterministic id: e.g. "AAPL_10K_2022Q3_2022-10-28__RiskFactors_c03"
            cid = f"{doc_id}__{slug}_c{section_chunk_index:02d}"
            if cid in used:                                  # deterministic guard (duplicate section names)
                cid = f"{cid}_{idx}"
            used.add(cid)
            out.append(
                apply_section_resolution(
                    Chunk.from_metadata(
                        meta, id=cid, doc_id=doc_id, chunk_index=idx,
                        section=span.section_name, section_index=section_index,
                        section_chunk_index=section_chunk_index, text=piece,
                        content_hash=hashlib.sha256(piece.encode("utf-8")).hexdigest(),
                    )
                )
            )
            idx += 1
            section_chunk_index += 1
    return out


def run_chunk(doc_id: str, *, base=None) -> list[Chunk]:
    cleaned = load_artifact("cleaned", doc_id, ext="txt", base=base)
    meta = DocMetadata(**load_artifact("metadata", doc_id, base=base))
    sections = [SectionSpan(**s) for s in load_artifact("sections", doc_id, base=base)]
    chunks = chunk_document(doc_id, meta, cleaned, sections)
    persist_artifact("chunks", doc_id, chunks, base=base)
    return chunks


def run_all(*, base=None) -> dict:
    return run_docs("chunk", list_artifacts("cleaned", "txt", base=base),
                    lambda d: run_chunk(d, base=base), base=base)


if __name__ == "__main__":
    r = run_all()
    if not r["results"] and not r["failed"]:
        print("Stage 5 chunk: no data/cleaned artifacts — run earlier stages first.")
    else:
        allc = [c for cs in r["results"] for c in cs]
        sizes = [len(c.text) for c in allc]
        print(f"Stage 5 chunk: {len(allc):,} chunks from {r['ok']} files ({r['failed']} failed); "
              f"chunk chars min {min(sizes, default=0)}, "
              f"avg {sum(sizes) // max(len(sizes), 1)}, max {max(sizes, default=0)}.")

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
from src.schemas import Chunk, DocMetadata, SectionSpan

SEPARATORS = ["\n\n", "\n", ". ", " ", ""]   # real boundaries first; "" hard-splits as last resort
_WORD = re.compile(r"[A-Za-z0-9]+")


def _slug(section_name: str) -> str:
    """'Risk Factors' -> 'RiskFactors' (CamelCase, alnum only, capped)."""
    s = "".join(w[:1].upper() + w[1:] for w in _WORD.findall(section_name))[:30]
    return s or "Section"


def make_splitter(chunk_size: int | None = None, chunk_overlap: int | None = None):
    # LangChain's chunk_size IS a maximum: it packs pieces up to the cap, so small
    # sections yield one short chunk and only long sections split. Default = settings cap.
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size or settings.chunk_max_chars,
        chunk_overlap=chunk_overlap or settings.chunk_overlap,
        separators=SEPARATORS,
        keep_separator=True,
        length_function=len,
    )


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
        for piece in splitter.split_text(cleaned[span.start:span.end]):   # children within the parent
            piece = piece.strip()
            if not piece:
                continue
            # section-aware, deterministic id: e.g. "AAPL_10K_2022Q3_2022-10-28__RiskFactors_c03"
            cid = f"{doc_id}__{slug}_c{section_chunk_index:02d}"
            if cid in used:                                  # deterministic guard (duplicate section names)
                cid = f"{cid}_{idx}"
            used.add(cid)
            out.append(
                Chunk.from_metadata(
                    meta, id=cid, doc_id=doc_id, chunk_index=idx,
                    section=span.section_name, section_index=section_index,
                    section_chunk_index=section_chunk_index, text=piece,
                    content_hash=hashlib.sha256(piece.encode("utf-8")).hexdigest(),
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

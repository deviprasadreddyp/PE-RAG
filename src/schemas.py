"""Pydantic models — the contracts passed between pipeline stages.

Design notes:
- All chunk metadata is **Chroma-safe**: only ``str``/``int``/``float``/``bool``
  scalars, never ``None`` (missing values are ``""`` or ``0``) and never lists.
- ``Chunk`` inherits every ``DocMetadata`` field, so a chunk carries the full
  filing metadata; ``Chunk.metadata()`` returns the flat dict to hand to Chroma
  (the ``text``/``embed_text`` are the document, not metadata).
- ``extra="forbid"`` everywhere, so a typo'd field fails loudly instead of being
  silently dropped.
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocMetadata(_Base):
    """Deterministically extracted per-filing metadata (Stage 3)."""

    company: str
    ticker: str
    form: str                       # normalized: "10-K" | "10-Q"
    filing_date: str                # ISO date the filing was filed, e.g. "2022-10-28"
    source_file: str                # original corpus filename
    report_period: str = ""         # period-end date from the header, e.g. "2022-09-24"
    fiscal_period: str = ""         # what the filing covers, e.g. "2022Q3" ("" if unknown)
    year: int = 0                   # fiscal year (0 = unknown)
    quarter: str = ""               # e.g. "Q3" ("" for a full-year 10-K without one)
    cik: str = ""
    source_url: str = ""
    document_id: str = ""           # stable filing id (== Chunk.doc_id); carried from Stage 3 on
    source: str = "SEC EDGAR"       # provenance, read from the filing header ("Source:")
    industry: str = ""              # GICS sector (curated reference table; "" if unknown)


class SectionSpan(_Base):
    """A detected SEC section and its character offsets in the cleaned text (Stage 4)."""

    section_name: str               # canonical name, e.g. "Risk Factors"
    item: str = ""                  # e.g. "Item 1A" ("" for a bucketed "Other" span)
    part: str = ""                  # parent Part in the section tree, e.g. "Part II" ("" if unknown)
    start: int
    end: int

    @model_validator(mode="after")
    def _end_after_start(self) -> "SectionSpan":
        if self.end < self.start:
            raise ValueError(f"section end ({self.end}) must be >= start ({self.start})")
        return self


class Chunk(DocMetadata):
    """A retrieval chunk: full filing metadata + the chunk's own fields (Stages 5-6)."""

    id: str                         # stable, unique: "{doc_id}_{chunk_index}"
    doc_id: str                     # e.g. "AAPL_10K_2024"
    chunk_index: int                # 0-based position in the whole document
    section: str                    # parent section this chunk came from
    section_index: int = 0          # 0-based index of the parent section (hierarchy: which section)
    section_chunk_index: int = 0    # 0-based position of this chunk WITHIN its section (child index)
    text: str                       # original text (for display + citation)
    embed_text: str = ""            # enriched text actually embedded (set in Stage 6)
    content_hash: str = ""          # sha256 of `text` — content-addressed dedup / change detection

    @classmethod
    def from_metadata(
        cls,
        meta: DocMetadata,
        *,
        id: str,
        doc_id: str,
        chunk_index: int,
        section: str,
        text: str,
        section_index: int = 0,
        section_chunk_index: int = 0,
        embed_text: str = "",
        content_hash: str = "",
    ) -> "Chunk":
        return cls(
            id=id,
            doc_id=doc_id,
            chunk_index=chunk_index,
            section=section,
            section_index=section_index,
            section_chunk_index=section_chunk_index,
            text=text,
            embed_text=embed_text,
            content_hash=content_hash,
            **meta.model_dump(),
        )

    def metadata(self) -> dict:
        """Flat, Chroma-safe metadata dict (excludes the document text fields)."""
        return self.model_dump(exclude={"text", "embed_text"})


class Citation(_Base):
    """A source the answer cites."""

    tag: str                        # inline tag, e.g. "[AAPL 10-K FY2024 · Item 7 MD&A]"
    ticker: str = ""
    company: str = ""
    form: str = ""
    fiscal_period: str = ""
    section: str = ""
    source_url: str = ""


class RetrievalResult(_Base):
    """A retrieved chunk with its fused relevance score (Phase 2 retrieval)."""

    chunk: Chunk
    score: float


class Answer(_Base):
    """The final grounded answer returned by the single Claude call (Phase 2)."""

    answer: str
    sources: list[Citation] = Field(default_factory=list)
    retrieved: list[RetrievalResult] = Field(default_factory=list)
    usage: dict = Field(default_factory=dict)   # input_tokens/output_tokens/cost_usd/latency_s


class Document(_Base):
    """A discovered source document (Stage 1) — powers incremental indexing via sha256."""

    doc_id: str
    filename: str
    sha256: str
    size: int
    status: str = "ok"


class EmbeddingRecord(_Base):
    """A chunk's embedding + its Chroma-safe metadata (Stage 7 output)."""

    chunk_id: str
    embedding: list[float]
    metadata: dict

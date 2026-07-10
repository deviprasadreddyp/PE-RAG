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
    accession_number: str = ""      # SEC accession number when present in the header
    is_amended: bool = False        # true for 10-K/A, 10-Q/A, or amendment-labeled filings
    is_restated: bool = False       # true when the header/filename marks the filing as restated
    entity_registrant_name: str = ""  # XBRL dei:EntityRegistrantName when present
    trading_symbol: str = ""        # XBRL dei:TradingSymbol when present
    document_type: str = ""         # XBRL dei:DocumentType, normalized where possible
    document_period_end_date: str = ""  # XBRL dei:DocumentPeriodEndDate
    document_fiscal_year_focus: int = 0  # XBRL dei:DocumentFiscalYearFocus
    document_fiscal_period_focus: str = ""  # XBRL dei:DocumentFiscalPeriodFocus ("FY", "Q1"...)
    current_fiscal_year_end_date: str = ""  # XBRL dei:CurrentFiscalYearEndDate, often "--09-30"
    amendment_flag: bool = False    # XBRL dei:AmendmentFlag; mirrors is_amended
    amendment_description: str = "" # XBRL dei:AmendmentDescription
    entity_incorporation_state_country_code: str = ""  # XBRL dei:EntityIncorporationStateCountryCode
    entity_common_stock_shares_outstanding: str = ""   # XBRL dei:EntityCommonStockSharesOutstanding


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
    section_original: str = ""      # initial section before deterministic post-chunk resolution
    section_confidence: float = 0.0 # confidence in final section label (0-1)
    section_source: str = ""        # initial_section | heading | content | table
    section_signals: str = ""       # pipe-delimited scalar signal list, Chroma-safe
    has_risk_heading: bool = False
    has_mda_heading: bool = False
    has_legal_heading: bool = False
    has_business_heading: bool = False
    has_financial_table: bool = False
    has_revenue_table: bool = False
    metadata_quality: float = 0.0   # deterministic quality score for ranking/debugging

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


# --- Phase 2: retrieval & generation contracts (see architecture/RETRIEVAL_DESIGN.md §3) -----

class QueryAnalysis(_Base):
    """Deterministic understanding of a user query (Stages 1-3; no LLM)."""

    query: str
    intents: list[str] = Field(default_factory=list)         # multi-label: Comparison/Trend/Risk/...
    companies: list[str] = Field(default_factory=list)       # tickers, e.g. ["AAPL", "TSLA"]
    years: list[int] = Field(default_factory=list)
    quarters: list[str] = Field(default_factory=list)        # e.g. ["Q3"]
    forms: list[str] = Field(default_factory=list)           # "10-K" / "10-Q"
    section_intent: list[str] = Field(default_factory=list)  # e.g. ["Risk Factors", "MD&A"]
    facets: list[str] = Field(default_factory=list)          # evidence facets: risk/financial/segments/...


class HardFilter(_Base):
    """Exact metadata constraints applied BEFORE ranking (Stage 4).

    Renders to a Chroma ``where`` filter and provides a ``matches`` predicate for BM25
    (which has no server-side filter). Empty lists mean "no constraint on that field".
    """

    tickers: list[str] = Field(default_factory=list)
    years: list[int] = Field(default_factory=list)
    quarters: list[str] = Field(default_factory=list)
    forms: list[str] = Field(default_factory=list)
    fiscal_periods: list[str] = Field(default_factory=list)  # e.g. ["2023Q4"] from explicit year+quarter queries

    @property
    def is_empty(self) -> bool:
        return not (self.tickers or self.years or self.quarters or self.forms or self.fiscal_periods)

    @property
    def where(self) -> dict:
        """Chroma-style where filter ($and of $in clauses); {} = no filter."""
        clauses: list[dict] = []
        if self.tickers:
            clauses.append({"ticker": {"$in": self.tickers}})
        period_clause = self._period_where()
        if period_clause:
            clauses.append(period_clause)
        if self.forms:
            clauses.append({"form": {"$in": self.forms}})
        if not clauses:
            return {}
        return clauses[0] if len(clauses) == 1 else {"$and": clauses}

    def _period_where(self) -> dict:
        """Year/quarter filter with fiscal_period aliases for SEC fiscal-calendar edge cases."""
        if self.fiscal_periods and self.years and self.quarters:
            return {
                "$or": [
                    {"$and": [
                        {"year": {"$in": self.years}},
                        {"quarter": {"$in": self.quarters}},
                    ]},
                    {"fiscal_period": {"$in": self.fiscal_periods}},
                ]
            }
        if self.years and self.quarters:
            return {"$and": [
                {"year": {"$in": self.years}},
                {"quarter": {"$in": self.quarters}},
            ]}
        if self.years:
            return {"year": {"$in": self.years}}
        if self.quarters:
            return {"quarter": {"$in": self.quarters}}
        if self.fiscal_periods:
            return {"fiscal_period": {"$in": self.fiscal_periods}}
        return {}

    def matches(self, md: dict) -> bool:
        """Predicate for BM25 candidates: does this chunk's metadata satisfy the filter?"""
        if self.tickers and md.get("ticker") not in self.tickers:
            return False
        if not self._matches_period(md):
            return False
        if self.forms and md.get("form") not in self.forms:
            return False
        return True

    def _matches_period(self, md: dict) -> bool:
        if not (self.years or self.quarters or self.fiscal_periods):
            return True
        exact_year_quarter = True
        if self.years:
            exact_year_quarter = exact_year_quarter and md.get("year") in self.years
        if self.quarters:
            exact_year_quarter = exact_year_quarter and md.get("quarter") in self.quarters
        fiscal_match = bool(self.fiscal_periods and md.get("fiscal_period") in self.fiscal_periods)
        return exact_year_quarter or fiscal_match


class RetrievalPlan(_Base):
    """How to retrieve, derived from the query type (Stage 5)."""

    mode: str = "global"                                     # "global" | "per_entity" | "per_period"
    per_entity_k: int = 0                                    # candidates per entity when not global
    section_boosts: list[str] = Field(default_factory=list)  # sections to boost, e.g. ["Risk Factors"]
    pool_size: int = 0                                       # fused pool size (0 -> settings.candidate_pool)
    facets: list[str] = Field(default_factory=list)          # required evidence facets for coverage


class Evidence(_Base):
    """A retrieved chunk tagged for the prompt and citations (Stages 10-11)."""

    evidence_id: str                                         # "E1", "E2", ...
    chunk: Chunk
    score: float = 0.0                                       # rerank (or fused) score
    tag: str = ""                                            # e.g. "[AAPL 10-K FY2024 · Risk Factors]"


class GuardrailResult(_Base):
    """Deterministic gate before prompt/LLM (Stage 12)."""

    ok: bool                                                 # True -> proceed to the single LLM call
    action: str = "accept"                                  # "accept" | "warn" | "reject"
    reason: str = ""                                        # why (for refusal / debug)
    confidence: str = ""                                   # "High" | "Medium" | "Low" (similarity band)


class PromptBundle(_Base):
    """The assembled single-call prompt (Stage 13)."""

    system: str
    user: str
    prompt_version: str


class AnswerBody(_Base):
    """Structured output of the single LLM call (Stage 14)."""

    executive_summary: str = Field(
        default="",
        description=(
            "Concise answer bullets. Every factual bullet or sentence must end with the evidence "
            "id(s) supporting it, such as [E1] or [E1][E3]."
        ),
    )
    comparison: str = Field(
        default="",
        description=(
            "Markdown table or bullets for comparison questions. Include a citation in every row "
            "or bullet; leave blank when not applicable."
        ),
    )
    supporting_evidence: str = Field(
        default="",
        description=(
            "Three to six concise evidence-backed bullets. Group related evidence ids in the same "
            "bullet when they support the same point, and include [E#] citations."
        ),
    )
    citations: list[str] = Field(
        default_factory=list,
        description=(
            "All evidence ids cited anywhere in executive_summary, comparison, supporting_evidence, "
            "or limitations, plus any additional evidence ids that materially support the answer. "
            "Include each id at most once, e.g. ['E1', 'E3']."
        ),
    )
    confidence: str = Field(default="", description="High / Medium / Low")
    limitations: str = Field(
        default="",
        description="Only state limitations grounded in missing or partial evidence; cite evidence when referenced.",
    )

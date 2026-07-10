"""Deterministic semantic section resolution for SEC chunks.

Initial section detection is intentionally conservative and offset-based, but SEC
filings often place meaningful business text under weak labels such as
``Exhibits``, ``Other``, or ``Form 10-K Summary``. This module performs a second,
post-chunk pass: extract heading/content signals from the chunk text, compare
them against the current label, and assign a final section with confidence and
Chroma-safe signal metadata. No LLMs, no randomness.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from src.schemas import Chunk


CANONICAL_SECTIONS = {
    "Risk Factors",
    "Management's Discussion and Analysis",
    "Legal Proceedings",
    "Business",
    "Financial Statements and Supplementary Data",
    "Cybersecurity",
    "Quantitative and Qualitative Disclosures About Market Risk",
}

WEAK_SECTIONS = {
    "",
    "Other",
    "Exhibits",
    "Form 10-K Summary",
    "Form 10-Q Summary",
    "Directors, Executive Officers and Corporate Governance",
    "Executive Compensation",
    "Security Ownership of Certain Beneficial Owners",
    "Certain Relationships and Related Transactions",
    "Selected Financial Data",
    "Disclosure Regarding Foreign Jurisdictions",
    "Exhibits and Financial Statement Schedules",
}

SECTION_PRIORITY = {
    "Risk Factors": 100,
    "Management's Discussion and Analysis": 95,
    "Legal Proceedings": 95,
    "Business": 90,
    "Financial Statements and Supplementary Data": 90,
    "Cybersecurity": 85,
    "Quantitative and Qualitative Disclosures About Market Risk": 75,
    "Selected Financial Data": 60,
    "Directors, Executive Officers and Corporate Governance": 30,
    "Form 10-K Summary": 20,
    "Form 10-Q Summary": 20,
    "Exhibits": 10,
    "Other": 5,
    "": 0,
}

CORE_METADATA_FIELDS = (
    "company",
    "ticker",
    "form",
    "filing_date",
    "source_file",
    "year",
    "section",
    "doc_id",
    "id",
)


@dataclass(frozen=True)
class SignalRule:
    section: str
    signal: str
    pattern: re.Pattern[str]
    confidence: float
    source: str = "heading"


@dataclass(frozen=True)
class SectionResolution:
    section: str
    original_section: str
    confidence: float
    source: str
    signals: tuple[str, ...]
    has_risk_heading: bool = False
    has_mda_heading: bool = False
    has_legal_heading: bool = False
    has_business_heading: bool = False
    has_financial_table: bool = False
    has_revenue_table: bool = False

    @property
    def section_signals(self) -> str:
        return "|".join(self.signals)


_RULES: tuple[SignalRule, ...] = (
    SignalRule(
        "Risk Factors", "item_1a_risk_factors",
        re.compile(r"\bitem\s+1a\.?\s+risk factors\b", re.I), 0.99,
    ),
    SignalRule(
        "Risk Factors", "risk_factors_heading",
        re.compile(r"(^|\n)\s*(?:risks?\s+related\s+to|risk factors)\b", re.I), 0.94,
    ),
    SignalRule(
        "Risk Factors", "risk_content",
        re.compile(r"\b(?:risks?|uncertainties|could adversely affect|production delays|strategic risk|"
                   r"regulatory risk|cybersecurity risk|technology risk)\b", re.I), 0.82,
        source="content",
    ),
    SignalRule(
        "Management's Discussion and Analysis", "item_7_mda",
        re.compile(r"\bitem\s+7\.?\s+management['’]?s discussion and analysis\b", re.I), 0.99,
    ),
    SignalRule(
        "Management's Discussion and Analysis", "mda_heading",
        re.compile(r"\bmanagement['’]?s discussion and analysis\b", re.I), 0.97,
    ),
    SignalRule(
        "Management's Discussion and Analysis", "results_of_operations",
        re.compile(r"\bresults of operations\b", re.I), 0.94,
    ),
    SignalRule(
        "Management's Discussion and Analysis", "liquidity_capital_resources",
        re.compile(r"\bliquidity and capital resources\b", re.I), 0.93,
    ),
    SignalRule(
        "Management's Discussion and Analysis", "trend_revenue_growth",
        re.compile(r"\b(?:revenue|revenues|sales|volume|subscriber|subscription|advertising).{0,80}"
                   r"(?:increased|decreased|declined|grew|growth|trend|change|outlook|monetiz)", re.I),
        0.86,
        source="content",
    ),
    SignalRule(
        "Legal Proceedings", "item_3_legal_proceedings",
        re.compile(r"\bitem\s+3\.?\s+legal proceedings\b", re.I), 0.99,
    ),
    SignalRule(
        "Legal Proceedings", "part_ii_item_1_legal",
        re.compile(r"\bpart\s+ii\.?\s+item\s+1\.?\s+legal proceedings\b", re.I), 0.99,
    ),
    SignalRule(
        "Legal Proceedings", "legal_proceedings_heading",
        re.compile(r"(^|\n|\bnote\s+\d+\s*[—-]\s*)legal proceedings\b", re.I), 0.97,
    ),
    SignalRule(
        "Legal Proceedings", "legal_content",
        re.compile(r"\b(?:lawsuits?|claims?|litigation|governmental investigations?|settlement|"
                   r"product liability|legal proceedings)\b", re.I), 0.84,
        source="content",
    ),
    SignalRule(
        "Business", "item_1_business",
        re.compile(r"\bitem\s+1\.?\s+business\b", re.I), 0.99,
    ),
    SignalRule(
        "Business", "business_overview",
        re.compile(r"\b(?:overview|description) of (?:the )?business\b|\bbusiness overview\b", re.I),
        0.93,
    ),
    SignalRule(
        "Business", "business_model_content",
        re.compile(r"\b(?:business model|products? and services|customers?|members?|membership|"
                   r"warehouses?|markets? served|service offerings)\b", re.I), 0.82,
        source="content",
    ),
    SignalRule(
        "Financial Statements and Supplementary Data", "item_8_financial_statements",
        re.compile(r"\bitem\s+8\.?\s+financial statements\b", re.I), 0.99,
    ),
    SignalRule(
        "Financial Statements and Supplementary Data", "financial_statement_heading",
        re.compile(r"\b(?:consolidated statements? of|financial statements?|balance sheets?|"
                   r"statements? of income|statements? of operations|statements? of cash flows)\b", re.I),
        0.94,
    ),
    SignalRule(
        "Financial Statements and Supplementary Data", "revenue_table",
        re.compile(r"\b(?:revenues?|net sales|advertising revenues?)\b.*(?:\||\$|\bin millions\b)", re.I),
        0.88,
        source="table",
    ),
    SignalRule(
        "Cybersecurity", "item_1c_cybersecurity",
        re.compile(r"\bitem\s+1c\.?\s+cybersecurity\b", re.I), 0.98,
    ),
    SignalRule(
        "Quantitative and Qualitative Disclosures About Market Risk", "item_7a_market_risk",
        re.compile(r"\bitem\s+7a\.?\s+quantitative and qualitative disclosures about market risk\b", re.I),
        0.96,
    ),
)


def _current_confidence(section: str) -> float:
    if section in WEAK_SECTIONS:
        return 0.35
    if section in CANONICAL_SECTIONS:
        return 0.82
    return 0.55


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _best_signal(text: str) -> tuple[SignalRule | None, tuple[str, ...]]:
    hits: list[SignalRule] = []
    for rule in _RULES:
        if rule.pattern.search(text):
            hits.append(rule)
    if not hits:
        return None, ()
    hits.sort(key=lambda r: (r.confidence, SECTION_PRIORITY.get(r.section, 0)), reverse=True)
    signals = tuple(dict.fromkeys(rule.signal for rule in hits))
    return hits[0], signals


def resolve_section(text: str, current_section: str) -> SectionResolution:
    """Resolve the final section label from current metadata + chunk text signals."""
    original = current_section or ""
    text_norm = _normalize(text)
    best, signals = _best_signal(text_norm)

    final = original or "Other"
    source = "initial_section"
    confidence = _current_confidence(final)
    if best is not None:
        current_priority = SECTION_PRIORITY.get(final, 50)
        best_priority = SECTION_PRIORITY.get(best.section, 50)
        weak = final in WEAK_SECTIONS
        materially_stronger = best.confidence >= confidence + 0.08 or best_priority > current_priority + 20
        same_family = best.section == final
        if weak or same_family or materially_stronger:
            final = best.section
            source = best.source
            confidence = best.confidence

    return SectionResolution(
        section=final,
        original_section=original,
        confidence=round(confidence, 3),
        source=source,
        signals=signals,
        has_risk_heading=any(s.startswith("item_1a") or "risk" in s for s in signals),
        has_mda_heading=any(s in {
            "item_7_mda", "mda_heading", "results_of_operations",
            "liquidity_capital_resources", "trend_revenue_growth",
        } for s in signals),
        has_legal_heading=any("legal" in s for s in signals),
        has_business_heading=any("business" in s or s == "business_model_content" for s in signals),
        has_financial_table=any("financial" in s or "statement" in s or "revenue_table" == s for s in signals),
        has_revenue_table=any("revenue" in s for s in signals),
    )


def metadata_quality(chunk: "Chunk", resolution: SectionResolution) -> float:
    """Simple deterministic metadata quality score for debugging and ranking bonuses."""
    present = 0
    for field in CORE_METADATA_FIELDS:
        value = getattr(chunk, field, "")
        if value not in ("", 0, None):
            present += 1
    completeness = present / len(CORE_METADATA_FIELDS)
    score = 0.70 * resolution.confidence + 0.30 * completeness
    return round(max(0.0, min(1.0, score)), 3)


def apply_section_resolution(chunk: "Chunk") -> "Chunk":
    """Return a copy of ``chunk`` with final section + Chroma-safe signal metadata."""
    resolution = resolve_section(chunk.text, chunk.section)
    original_section = chunk.section_original or resolution.original_section
    updates = {
        "section": resolution.section,
        "section_original": original_section,
        "section_confidence": resolution.confidence,
        "section_source": resolution.source,
        "section_signals": resolution.section_signals,
        "has_risk_heading": resolution.has_risk_heading,
        "has_mda_heading": resolution.has_mda_heading,
        "has_legal_heading": resolution.has_legal_heading,
        "has_business_heading": resolution.has_business_heading,
        "has_financial_table": resolution.has_financial_table,
        "has_revenue_table": resolution.has_revenue_table,
    }
    updated = chunk.model_copy(update=updates)
    return updated.model_copy(update={"metadata_quality": metadata_quality(updated, resolution)})

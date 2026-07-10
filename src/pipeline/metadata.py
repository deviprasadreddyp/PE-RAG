"""Stage 3 — deterministic metadata extraction (NEVER an LLM).

Build a ``DocMetadata`` from the filing's header block (in ``data/raw/``) plus the
filename. The header wins where both provide a value; the filename backfills what
the header lacks (the corpus is missing ``Report Period`` / ``Quarter`` on ~22% of
files — see architecture/corpus_notes.md). ``form`` is normalized to exactly
``10-K`` / ``10-Q``. Persist to ``data/metadata/<doc_id>.json``.

Run standalone:  python -m src.pipeline.metadata
"""

from __future__ import annotations

import html
import re

from src.observability import list_artifacts, load_artifact, persist_artifact, run_docs
from src.pipeline.clean import split_header_body
from src.pipeline.ingest import FILENAME, SUFFIX
from src.reference import sector_for
from src.schemas import DocMetadata


def parse_header(header: str) -> dict[str, str]:
    """Header lines 'Label: value' -> {label: value} (split on the first colon)."""
    out: dict[str, str] = {}
    for line in header.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            if key:
                out[key] = val.strip()
    return out


def parse_filename(doc_id: str) -> dict[str, str]:
    """Pull ticker/form/period/date from the filename (empty dict if it doesn't match)."""
    m = FILENAME.match(doc_id + SUFFIX)
    return {k: (v or "") for k, v in m.groupdict().items()} if m else {}


def normalize_form(text: str) -> str:
    """'10-K (Annual Report)' / '10K' -> '10-K'; '10-Q' / '10Q' -> '10-Q'; else ''."""
    m = re.search(r"10-?\s*([KQ])", text, re.I)
    return f"10-{m.group(1).upper()}" if m else ""


def _bool(text: str) -> bool:
    return str(text).strip().lower() in {"true", "1", "yes", "y"}


def is_amended_filing(*sources: str) -> bool:
    """Whether header/filename marks this as an amended 10-K/A or 10-Q/A."""
    text = " ".join(s or "" for s in sources)
    return bool(re.search(r"10-?\s*[KQ]\s*/\s*A\b|\bamend(?:ed|ment)?\b", text, re.I))


def is_restated_filing(*sources: str) -> bool:
    """Whether header/filename explicitly labels the filing as restated."""
    text = " ".join(s or "" for s in sources)
    return bool(re.search(r"\brestat(?:e|ed|ement|ements|ing)\b", text, re.I))


def _quarter(fiscal_period: str) -> str:
    m = re.search(r"Q([1-4])", fiscal_period, re.I)
    return f"Q{m.group(1)}" if m else ""


def _year(*sources: str) -> int:
    for s in sources:
        m = re.search(r"(?:19|20)\d{2}", s or "")
        if m:
            return int(m.group(0))
    return 0


_PROSE = re.compile(r"UNITED STATES\s*SECURITIES AND EXCHANGE COMMISSION|FORM 10-[KQ]", re.I)
_XBRL_TAGS = {
    "EntityRegistrantName": "entity_registrant_name",
    "TradingSymbol": "trading_symbol",
    "EntityCentralIndexKey": "cik",
    "DocumentType": "document_type",
    "DocumentPeriodEndDate": "document_period_end_date",
    "DocumentFiscalYearFocus": "document_fiscal_year_focus",
    "DocumentFiscalPeriodFocus": "document_fiscal_period_focus",
    "CurrentFiscalYearEndDate": "current_fiscal_year_end_date",
    "AmendmentFlag": "amendment_flag",
    "AmendmentDescription": "amendment_description",
    "EntityIncorporationStateCountryCode": "entity_incorporation_state_country_code",
    "EntityCommonStockSharesOutstanding": "entity_common_stock_shares_outstanding",
}


def _strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def _xbrl_tag_value(raw: str, tag: str) -> str:
    """Extract a DEI/XBRL fact from standard XML or inline-XBRL, if the corpus has it."""
    full = re.compile(
        rf"<(?:[A-Za-z0-9_-]+:)?{tag}\b[^>]*>(.*?)</(?:[A-Za-z0-9_-]+:)?{tag}>",
        re.I | re.S,
    )
    m = full.search(raw)
    if m:
        return _strip_tags(m.group(1))
    inline = re.compile(
        rf"<(?:[A-Za-z0-9_-]+:)?non(?:Numeric|Fraction)\b[^>]*\bname=[\"'](?:dei:)?{tag}[\"'][^>]*>"
        rf"(.*?)</(?:[A-Za-z0-9_-]+:)?non(?:Numeric|Fraction)>",
        re.I | re.S,
    )
    m = inline.search(raw)
    return _strip_tags(m.group(1)) if m else ""


def _date_yyyymmdd(text: str) -> str:
    m = re.match(r"(\d{4})(\d{2})(\d{2})$", text or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def _leading_xbrl_preamble(body: str) -> str:
    m = _PROSE.search(body)
    lead = body[:m.start()] if m else body[:12000]
    return re.sub(r"\s+", "", lead)


def _extract_compact_preamble(body: str) -> dict:
    """Extract high-value facts from the corpus' compressed leading XBRL preamble.

    Example shape:
    ``aapl-20220326false2022Q20000320193--09-24...``
    """
    compact = _leading_xbrl_preamble(body)
    patterns = [
        # aapl-20220326false2022Q20000320193--09-24
        r"[a-z0-9.-]+-(?P<period>\d{8})(?P<amend>true|false)"
        r"(?P<fy>(?:19|20)\d{2})(?P<fp>FY|Q[1-4])(?P<cik>\d{10})(?P<fy_end>--\d{2}-\d{2})?",
        # tsla-20241231false00013186052024FY
        r"[a-z0-9.-]+-(?P<period>\d{8})(?P<amend>true|false)"
        r"(?P<cik>\d{10})(?P<fy>(?:19|20)\d{2})(?P<fp>FY|Q[1-4])(?P<fy_end>--\d{2}-\d{2})?",
        # jpm-202512310000019617FALSE2025FY
        r"[a-z0-9.-]+-(?P<period>\d{8})(?P<cik>\d{10})(?P<amend>true|false)"
        r"(?P<fy>(?:19|20)\d{2})(?P<fp>FY|Q[1-4])(?P<fy_end>--\d{2}-\d{2})?",
    ]
    m = next((re.search(p, compact, re.I) for p in patterns if re.search(p, compact, re.I)), None)
    if not m:
        return {}
    return {
        "document_period_end_date": _date_yyyymmdd(m.group("period")),
        "amendment_flag": _bool(m.group("amend")),
        "document_fiscal_year_focus": int(m.group("fy")),
        "document_fiscal_period_focus": m.group("fp").upper(),
        "cik": m.group("cik"),
        "current_fiscal_year_end_date": m.group("fy_end") or "",
    }


def _extract_cover_facts(body: str) -> dict:
    """Cover-page fallbacks for useful DEI facts when clean XBRL tags are absent."""
    facts: dict[str, str] = {}
    # "California | | 94-2404110" style cover table.
    m = re.search(r"\n([A-Z][A-Za-z .'-]{1,40})\s*\|\s*\|\s*\d{2}-\d{7}", body)
    if m:
        facts["entity_incorporation_state_country_code"] = m.group(1).strip()
    # Common wording near the cover page; keep as a string because filings vary in scale/commas.
    m = re.search(
        r"(\d[\d,]{3,})\s+shares\s+of\s+(?:the\s+)?(?:registrant'?s\s+)?common stock",
        body,
        re.I,
    )
    if m:
        facts["entity_common_stock_shares_outstanding"] = m.group(1)
    return facts


def extract_xbrl_metadata(raw: str) -> dict:
    """Preserve useful XBRL/cover facts as metadata; never feed the tag soup to embeddings."""
    _, body = split_header_body(raw)
    facts: dict = {}
    for tag, field in _XBRL_TAGS.items():
        value = _xbrl_tag_value(raw, tag)
        if value:
            facts[field] = value
    facts.update({k: v for k, v in _extract_compact_preamble(body).items() if v not in ("", 0)})
    for k, v in _extract_cover_facts(body).items():
        facts.setdefault(k, v)

    if "document_type" in facts:
        facts["document_type"] = normalize_form(str(facts["document_type"])) or str(facts["document_type"])
    if "document_fiscal_year_focus" in facts:
        try:
            facts["document_fiscal_year_focus"] = int(facts["document_fiscal_year_focus"])
        except (TypeError, ValueError):
            facts["document_fiscal_year_focus"] = 0
    if "amendment_flag" in facts:
        facts["amendment_flag"] = _bool(str(facts["amendment_flag"]))
    return facts


def build_metadata(doc_id: str, raw: str) -> DocMetadata:
    header, _ = split_header_body(raw)
    h = parse_header(header)
    fn = parse_filename(doc_id)
    x = extract_xbrl_metadata(raw)

    ticker = h.get("Ticker") or x.get("trading_symbol") or fn.get("ticker", "")
    # We keep the field name `form` (used across filters, citations, tests). The header
    # labels it "Filing Type"; we normalize its value to exactly "10-K" / "10-Q".
    filing_type = h.get("Filing Type", "")
    form = normalize_form(filing_type) or normalize_form(x.get("document_type", "")) or normalize_form(fn.get("form", ""))
    filing_date = h.get("Filing Date") or fn.get("date", "")
    report_period = h.get("Report Period") or x.get("document_period_end_date", "")
    # The header's "Quarter" field holds a fiscal period like "2022Q3"; backfill from the filename.
    fiscal_period = h.get("Quarter") or fn.get("period", "")
    fiscal_year = int(x.get("document_fiscal_year_focus") or 0) or _year(fiscal_period, report_period, filing_date)
    fiscal_focus = str(x.get("document_fiscal_period_focus", "")).upper()
    quarter = fiscal_focus if re.fullmatch(r"Q[1-4]", fiscal_focus) else _quarter(fiscal_period)
    if fiscal_focus == "FY":
        quarter = ""
    fy_end = x.get("current_fiscal_year_end_date", "")
    if not fy_end and re.match(r"\d{4}-\d{2}-\d{2}$", report_period or ""):
        fy_end = "--" + report_period[5:]
    amendment_flag = bool(x.get("amendment_flag")) or is_amended_filing(filing_type, doc_id)
    return DocMetadata(
        company=h.get("Company") or x.get("entity_registrant_name") or ticker,
        ticker=ticker,
        form=form,
        filing_date=filing_date,
        report_period=report_period,
        fiscal_period=fiscal_period,
        year=fiscal_year,
        quarter=quarter,
        cik=h.get("CIK") or x.get("cik", ""),
        source_url=h.get("URL", ""),
        source_file=doc_id + SUFFIX,
        document_id=doc_id,                          # stable filing id (== chunk.doc_id)
        source=h.get("Source") or "SEC EDGAR",       # provenance from the header
        industry=sector_for(ticker),                 # curated GICS sector ("" if unknown)
        accession_number=h.get("Accession Number") or h.get("Accession", ""),
        is_amended=amendment_flag,
        is_restated=is_restated_filing(filing_type, doc_id, str(x.get("amendment_description", ""))),
        entity_registrant_name=x.get("entity_registrant_name") or h.get("Company") or ticker,
        trading_symbol=x.get("trading_symbol") or ticker,
        document_type=x.get("document_type") or form,
        document_period_end_date=x.get("document_period_end_date") or report_period,
        document_fiscal_year_focus=int(x.get("document_fiscal_year_focus") or fiscal_year or 0),
        document_fiscal_period_focus=fiscal_focus,
        current_fiscal_year_end_date=fy_end,
        amendment_flag=amendment_flag,
        amendment_description=x.get("amendment_description", ""),
        entity_incorporation_state_country_code=x.get("entity_incorporation_state_country_code", ""),
        entity_common_stock_shares_outstanding=x.get("entity_common_stock_shares_outstanding", ""),
    )


def run_metadata(doc_id: str, *, base=None) -> DocMetadata:
    raw = load_artifact("raw", doc_id, ext="txt", base=base)
    meta = build_metadata(doc_id, raw)
    persist_artifact("metadata", doc_id, meta, base=base)
    return meta


def run_all(*, base=None) -> dict:
    return run_docs("metadata", list_artifacts("raw", "txt", base=base),
                    lambda d: run_metadata(d, base=base), base=base)


if __name__ == "__main__":
    r = run_all()
    if not r["results"] and not r["failed"]:
        print("Stage 3 metadata: no data/raw artifacts — run `python -m src.pipeline.ingest` first.")
    else:
        with_period = sum(1 for m in r["results"] if m.fiscal_period)
        print(f"Stage 3 metadata: {r['ok']} extracted, {r['failed']} failed; "
              f"fiscal_period present on {with_period}/{r['ok']} after backfill.")

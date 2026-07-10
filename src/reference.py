"""Curated reference data — small, hand-maintained lookup tables.

The filings themselves do NOT carry an industry/sector field (the header has
Company/Ticker/Filing Type/CIK/URL but no SIC or GICS code — see a raw file in
``data/raw/``). Sector is genuinely external to the corpus, so we OWN it here as a
curated table keyed by ticker for the 54 issuers in this corpus, using current
(post-2023 GICS revision) sector labels. Unknown tickers fall back to ``""`` —
we never guess. This powers sector-level filtering/comparison in Phase 2
(e.g. "compare gross margins across Information Technology issuers").
"""

from __future__ import annotations

# GICS sector per corpus ticker (11-sector scheme; current, post-2023 revision —
# e.g. payments V/MA/AXP and staples-retail WMT/COST/TGT sit where GICS places them today).
SECTOR_BY_TICKER: dict[str, str] = {
    # Information Technology
    "AAPL": "Information Technology", "ADBE": "Information Technology",
    "AMD": "Information Technology", "CRM": "Information Technology",
    "CSCO": "Information Technology", "IBM": "Information Technology",
    "INTC": "Information Technology", "MSFT": "Information Technology",
    "NVDA": "Information Technology", "ORCL": "Information Technology",
    # Health Care
    "ABBV": "Health Care", "JNJ": "Health Care", "LLY": "Health Care",
    "MRK": "Health Care", "PFE": "Health Care", "TMO": "Health Care",
    "UNH": "Health Care",
    # Financials
    "AXP": "Financials", "BAC": "Financials", "BLK": "Financials",
    "BRK": "Financials", "GS": "Financials", "JPM": "Financials",
    "MA": "Financials", "MS": "Financials", "V": "Financials",
    # Consumer Discretionary
    "AMZN": "Consumer Discretionary", "HD": "Consumer Discretionary",
    "MCD": "Consumer Discretionary", "NKE": "Consumer Discretionary",
    "SBUX": "Consumer Discretionary", "TSLA": "Consumer Discretionary",
    # Consumer Staples
    "COST": "Consumer Staples", "KO": "Consumer Staples", "PEP": "Consumer Staples",
    "PG": "Consumer Staples", "TGT": "Consumer Staples", "WMT": "Consumer Staples",
    # Communication Services
    "CMCSA": "Communication Services", "DIS": "Communication Services",
    "GOOG": "Communication Services", "META": "Communication Services",
    "NFLX": "Communication Services", "T": "Communication Services",
    "VZ": "Communication Services",
    # Industrials
    "BA": "Industrials", "CAT": "Industrials", "DE": "Industrials",
    "GE": "Industrials", "LMT": "Industrials", "RTX": "Industrials",
    "UPS": "Industrials",
    # Energy
    "CVX": "Energy", "XOM": "Energy",
}


def sector_for(ticker: str) -> str:
    """GICS sector for a ticker, or ``""`` if we don't have a curated entry."""
    return SECTOR_BY_TICKER.get(ticker.upper(), "")


# --- SEC form structure (canonical section names + Part tree) --------------------
#
# 10-K item numbers are GLOBALLY unambiguous (Item 7 is always MD&A), so we can map
# them to canonical names and to their Part (fixed regulatory structure). 10-Q item
# numbers REPEAT across Part I / Part II (Item 1 = "Financial Statements" in Part I
# but "Legal Proceedings" in Part II), and Part boundaries are unreliable to detect
# in these inline-formatted filings — so for 10-Q we keep the detected title and do
# not guess. See src/pipeline/sections.py.

import re as _re

SEC_10K_ITEM_NAMES: dict[str, str] = {
    "Item 1": "Business",
    "Item 1A": "Risk Factors",
    "Item 1B": "Unresolved Staff Comments",
    "Item 1C": "Cybersecurity",
    "Item 2": "Properties",
    "Item 3": "Legal Proceedings",
    "Item 4": "Mine Safety Disclosures",
    "Item 5": "Market for Registrant's Common Equity",
    "Item 6": "Selected Financial Data",
    "Item 7": "Management's Discussion and Analysis",
    "Item 7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "Item 8": "Financial Statements and Supplementary Data",
    "Item 9": "Changes in and Disagreements with Accountants",
    "Item 9A": "Controls and Procedures",
    "Item 9B": "Other Information",
    "Item 9C": "Disclosure Regarding Foreign Jurisdictions",
    "Item 10": "Directors, Executive Officers and Corporate Governance",
    "Item 11": "Executive Compensation",
    "Item 12": "Security Ownership of Certain Beneficial Owners",
    "Item 13": "Certain Relationships and Related Transactions",
    "Item 14": "Principal Accountant Fees and Services",
    "Item 15": "Exhibits and Financial Statement Schedules",
    "Item 16": "Form 10-K Summary",
}

# Fixed 10-K Part -> item-range structure (the "section tree" backbone).
_PART_10K_RANGES = (("Part I", 1, 4), ("Part II", 5, 9), ("Part III", 10, 14), ("Part IV", 15, 99))


def canonical_section_name(form: str, item: str, fallback: str = "") -> str:
    """Canonical section name for a normalized item ("Item 1A").

    10-K: mapped to the standard SEC name. 10-Q (Part-ambiguous): return ``fallback``
    (the detected title) rather than guess. Unknown 10-K items fall back too.
    """
    if form == "10-K":
        name = SEC_10K_ITEM_NAMES.get(item)
        if name:
            return name
    low = fallback.lower()
    if "risk factor" in low:
        return "Risk Factors"
    if "legal proceeding" in low:
        return "Legal Proceedings"
    if "management" in low and "analysis" in low:
        return "Management's Discussion and Analysis"
    if "financial statement" in low:
        return "Financial Statements and Supplementary Data"
    if "market risk" in low:
        return "Quantitative and Qualitative Disclosures About Market Risk"
    if "control" in low and "procedure" in low:
        return "Controls and Procedures"
    if "exhibit" in low:
        return "Exhibits"
    if low.strip() == "business":
        return "Business"
    return fallback


def part_for_10k_item(item: str) -> str:
    """Parent Part ("Part I".."Part IV") for a 10-K item, from the fixed SEC structure."""
    m = _re.match(r"Item (\d+)", item)
    if not m:
        return ""
    n = int(m.group(1))
    for name, lo, hi in _PART_10K_RANGES:
        if lo <= n <= hi:
            return name
    return ""


# --- Company name -> ticker dictionary (corpus issuers) --------------------------
#
# Used by Stage 3 metadata extraction to map free text to tickers. NAMES are matched
# case-insensitively; the TICKER symbol itself is matched only in UPPERCASE and only
# for len>=2, so common English words that happen to be tickers ("cost" -> COST,
# "cat" -> CAT) are NOT false-matched from lowercase prose (users type COST/CAT).

_COMPANY_NAMES: dict[str, str] = {
    "apple": "AAPL", "apple inc": "AAPL",
    "abbvie": "ABBV", "abbvie inc": "ABBV",
    "adobe": "ADBE", "adobe inc": "ADBE",
    "amd": "AMD", "advanced micro devices": "AMD", "advanced micro devices inc": "AMD",
    "amazon": "AMZN", "amazon.com": "AMZN", "amazon.com inc": "AMZN",
    "american express": "AXP", "amex": "AXP",
    "boeing": "BA",
    "bank of america": "BAC",
    "blackrock": "BLK",
    "berkshire": "BRK", "berkshire hathaway": "BRK",
    "caterpillar": "CAT",
    "comcast": "CMCSA",
    "costco": "COST",
    "salesforce": "CRM",
    "cisco": "CSCO",
    "chevron": "CVX",
    "deere": "DE", "john deere": "DE",
    "disney": "DIS", "walt disney": "DIS",
    "general electric": "GE", "ge aerospace": "GE",
    "google": "GOOG", "alphabet": "GOOG", "alphabet inc": "GOOG",
    "goldman sachs": "GS", "goldman": "GS",
    "home depot": "HD",
    "ibm": "IBM", "international business machines": "IBM",
    "intel": "INTC", "intel corporation": "INTC",
    "johnson & johnson": "JNJ", "johnson and johnson": "JNJ", "j&j": "JNJ",
    "jpmorgan": "JPM", "jp morgan": "JPM", "j.p. morgan": "JPM",
    "jpmorgan chase": "JPM", "jpmorgan chase & co": "JPM", "jpmorgan chase and co": "JPM",
    "coca-cola": "KO", "coca cola": "KO", "coke": "KO",
    "eli lilly": "LLY", "eli lilly and company": "LLY", "lilly": "LLY",
    "lockheed": "LMT", "lockheed martin": "LMT",
    "mastercard": "MA",
    "mcdonald's": "MCD", "mcdonalds": "MCD",
    "meta": "META", "facebook": "META",
    "merck": "MRK", "merck & co": "MRK", "merck and co": "MRK",
    "morgan stanley": "MS",
    "microsoft": "MSFT", "microsoft corporation": "MSFT",
    "netflix": "NFLX",
    "nike": "NKE",
    "nvidia": "NVDA", "nvidia corporation": "NVDA",
    "oracle": "ORCL",
    "pepsi": "PEP", "pepsico": "PEP",
    "pfizer": "PFE", "pfizer inc": "PFE",
    "procter & gamble": "PG", "procter and gamble": "PG", "p&g": "PG",
    "raytheon": "RTX",
    "starbucks": "SBUX",
    "at&t": "T",
    "target": "TGT",
    "thermo fisher": "TMO", "thermo fisher scientific": "TMO",
    "tesla": "TSLA", "tesla inc": "TSLA",
    "unitedhealth": "UNH", "united health": "UNH", "unitedhealth group": "UNH",
    "united parcel service": "UPS",
    "visa": "V",
    "verizon": "VZ",
    "walmart": "WMT", "wal-mart": "WMT",
    "exxon": "XOM", "exxonmobil": "XOM", "exxon mobil": "XOM",
    "exxon mobil corporation": "XOM",
}

_COMPANY_GROUPS: list[tuple[str, list[str]]] = [
    (r"\b(?:major\s+)?(?:pharma|pharmaceutical|drugmaker|drug\s+maker)s?\b",
     ["ABBV", "JNJ", "LLY", "MRK", "PFE"]),
]

# Uppercase ticker symbols matched as standalone tokens (case-sensitive), longest first.
_UPPER_TICKERS: list[str] = sorted(
    (t for t in SECTOR_BY_TICKER if len(t) >= 2), key=len, reverse=True
)


def match_companies(text: str) -> list[str]:
    """Tickers named in ``text`` (by company name OR uppercase symbol), first-appearance order."""
    low = text.lower()
    pos: dict[str, int] = {}

    def _note(ticker: str, i: int) -> None:
        if ticker not in pos or i < pos[ticker]:
            pos[ticker] = i

    # 1. company names — case-insensitive, non-alphanumeric boundaries (so "j&j"/"at&t" work)
    for alias, ticker in _COMPANY_NAMES.items():
        m = _re.search(r"(?<![a-z0-9])" + _re.escape(alias) + r"(?![a-z0-9])", low)
        if m:
            _note(ticker, m.start())

    # 2. curated company groups, e.g. "major pharmaceutical companies"
    for pattern, tickers in _COMPANY_GROUPS:
        m = _re.search(pattern, low)
        if m:
            for offset, ticker in enumerate(tickers):
                _note(ticker, m.start() + offset)

    # 3. uppercase ticker symbols — case-sensitive, standalone (avoids "cost"->COST etc.)
    for t in _UPPER_TICKERS:
        m = _re.search(r"(?<![A-Za-z0-9])" + t + r"(?![A-Za-z0-9])", text)
        if m:
            _note(t, m.start())
    return [t for t, _ in sorted(pos.items(), key=lambda kv: kv[1])]

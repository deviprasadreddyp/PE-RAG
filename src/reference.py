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

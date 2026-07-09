"""Reference-table tests: sector lookup is case-insensitive, complete for the corpus, safe on misses."""

import json
from pathlib import Path

from src.reference import SECTOR_BY_TICKER, sector_for

VALID_GICS = {
    "Information Technology", "Health Care", "Financials", "Consumer Discretionary",
    "Consumer Staples", "Communication Services", "Industrials", "Energy",
    "Materials", "Utilities", "Real Estate",
}


def test_sector_lookup_and_fallback():
    assert sector_for("AAPL") == "Information Technology"
    assert sector_for("aapl") == "Information Technology"        # case-insensitive
    assert sector_for("XOM") == "Energy"
    assert sector_for("NOTATICKER") == ""                        # never guess


def test_all_sectors_are_valid_gics():
    assert set(SECTOR_BY_TICKER.values()) <= VALID_GICS


def test_every_corpus_ticker_has_a_sector():
    manifest = Path("edgar_corpus/manifest.json")
    if not manifest.exists():                                    # corpus not present in this checkout
        return
    tickers = {f.split("_")[0] for f in json.loads(manifest.read_text("utf-8"))["files"]}
    missing = {t for t in tickers if not sector_for(t)}
    assert not missing, f"tickers with no curated sector: {sorted(missing)}"

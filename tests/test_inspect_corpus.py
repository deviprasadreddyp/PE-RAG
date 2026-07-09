"""Tests for the pure helpers in the corpus-inspection spike (no corpus needed)."""

from scripts.inspect_corpus import (
    detect_items,
    find_prose_start,
    header_fields_present,
    split_header_body,
)

SEP = "=" * 60


def test_split_header_body():
    header, body = split_header_body(f"Company: X\nTicker: Y\n{SEP}\nBODY TEXT")
    assert "Company: X" in header and "BODY" in body
    # no separator -> everything is header, body empty
    assert split_header_body("no sep here") == ("no sep here", "")


def test_header_fields_present():
    hdr = "Company: Apple\nTicker: AAPL\nFiling Type: 10-K\nCIK: 0000320193\n"
    got = header_fields_present(hdr)
    assert got["Company"] and got["Ticker"] and got["CIK"]
    assert not got["Report Period"] and not got["Quarter"]


def test_find_prose_start():
    body = "0000320193us-gaap:Foo ... noise ... FORM 10-K rest of filing"
    idx = find_prose_start(body)
    assert idx >= 0 and body[idx:].startswith("FORM 10-K")
    assert find_prose_start("only xbrl tag soup, no anchor") == -1


def test_detect_items_normalizes_and_dedupes():
    text = (
        "TABLE OF CONTENTS Item 1A Item 7\n"
        "Item 1A. Risk Factors\n"
        "ITEM 7. Management Discussion\n"
        "Item 8. Financial Statements\n"
    )
    items = detect_items(text)
    assert items == ["Item 1A", "Item 7", "Item 8"]   # normalized case, first-seen order, deduped

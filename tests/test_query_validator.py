"""Stage 1 tests: reject empty/short/long/control/no-alnum; normalize valid queries."""

import pytest

from src.config import settings
from src.retrieval.query_validator import QueryError, validate_query


def test_valid_query_is_normalized():
    assert validate_query("  Compare   Apple\tand   Tesla  ") == "Compare Apple and Tesla"


def test_empty_and_whitespace_rejected():
    for bad in ("", "   ", "\n\t "):
        with pytest.raises(QueryError):
            validate_query(bad)


def test_too_short_rejected():
    with pytest.raises(QueryError):
        validate_query("ab")                          # < min_query_chars (3)


def test_too_long_rejected():
    with pytest.raises(QueryError):
        validate_query("a " * (settings.max_query_chars))   # well over the cap


def test_control_characters_rejected():
    with pytest.raises(QueryError):
        validate_query("revenue\x00growth")


def test_no_alphanumeric_rejected():
    with pytest.raises(QueryError):
        validate_query("!!! ??? ...")


def test_non_string_rejected():
    with pytest.raises(QueryError):
        validate_query(None)                          # type: ignore[arg-type]


def test_boundary_min_length_ok():
    assert validate_query("AMD") == "AMD"             # exactly min_query_chars

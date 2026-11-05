"""Unit tests for the Query Understanding module (agent/query_parser.py).

Covers the four acceptance cases from docs/function_contractsv2.md and
regression cases for the whole-word ticker matching fix.

Run from the repository root:
    python -m pytest tests/test_query_parser.py -v
"""

import json

import pytest

from agent.query_parser import understand_query


# --------------------------------------------------
# Acceptance cases from the function contract
# --------------------------------------------------

def test_complete_filters():
    """Microsoft Q3 FY2026 -> all three filters extracted."""
    assert understand_query("Microsoft Q3 FY2026") == {
        "ticker": "MSFT",
        "fiscal_year": 2026,
        "fiscal_period": "Q3",
    }


def test_partial_filters():
    """Company + year only -> period is None."""
    assert understand_query("Microsoft FY2025") == {
        "ticker": "MSFT",
        "fiscal_year": 2025,
        "fiscal_period": None,
    }


def test_no_recognizable_filters():
    """No company / year / period -> all None."""
    assert understand_query("Revenue performance") == {
        "ticker": None,
        "fiscal_year": None,
        "fiscal_period": None,
    }


@pytest.mark.parametrize("bad_input", ["", "   ", None, 123, 3.14])
def test_invalid_input_raises(bad_input):
    """Empty or non-string input must raise ValueError."""
    with pytest.raises(ValueError):
        understand_query(bad_input)


# --------------------------------------------------
# Output shape guarantees
# --------------------------------------------------

def test_always_returns_three_keys():
    """The result always contains exactly the three required keys."""
    result = understand_query("Any arbitrary question")
    assert set(result.keys()) == {"ticker", "fiscal_year", "fiscal_period"}


def test_output_is_json_serializable():
    """The result must survive a JSON round-trip for the API layer."""
    result = understand_query("Microsoft Q3 FY2026")
    assert json.loads(json.dumps(result)) == result


# --------------------------------------------------
# Ticker matching: legitimate cases
# --------------------------------------------------

def test_company_name_case_insensitive():
    """Company names match regardless of case."""
    assert understand_query("nvidia q4 fy2027")["ticker"] == "NVDA"


def test_ticker_symbol_directly():
    """Raw ticker symbols are recognized."""
    assert understand_query("MSFT Q3 FY2026")["ticker"] == "MSFT"
    assert understand_query("msft q3 fy2026")["ticker"] == "MSFT"


def test_possessive_company_name():
    """A possessive form such as "Apple's" still matches."""
    assert understand_query("Apple's revenue Q1 fiscal year 2024")["ticker"] == "AAPL"


# --------------------------------------------------
# Ticker matching: whole-word regression cases
# --------------------------------------------------

def test_no_false_positive_on_metadata():
    """"meta" must not match inside "metadata"."""
    assert understand_query(
        "What is the metadata retention policy?"
    )["ticker"] is None


def test_no_false_positive_on_pineapple():
    """"apple" must not match inside "pineapple"."""
    assert understand_query("pineapple revenue")["ticker"] is None

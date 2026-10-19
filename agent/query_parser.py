
import pytest

from agent.query_parser import understand_query


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            "Microsoft Q3 FY2026",
            {"ticker": "MSFT", "fiscal_year": 2026, "fiscal_period": "Q3"},
        ),
        (
            "Microsoft FY2025",
            {"ticker": "MSFT", "fiscal_year": 2025, "fiscal_period": None},
        ),
        (
            "Revenue performance",
            {"ticker": None, "fiscal_year": None, "fiscal_period": None},
        ),
    ],
)
def test_understand_query_filters(question, expected):
    assert understand_query(question) == expected


@pytest.mark.parametrize("invalid_query", ["", None, 123, []])
def test_understand_query_rejects_invalid_input(invalid_query):
    with pytest.raises(ValueError):
        understand_query(invalid_query)

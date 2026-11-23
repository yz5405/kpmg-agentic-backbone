from unittest.mock import patch

import pytest

from agent.tools.coverage_tool import precheck_coverage


@pytest.mark.parametrize("status", [
    "all_hit",
    "partial",
    "none",
    "unresolved",
    "no_target",
])
def test_precheck_coverage_passes_through_result(status):
    query = "What was Microsoft's revenue?"
    filters = {"accession_number": ["A-MSFT-Q3"]} if status == "all_hit" else None
    expected = {"status": status, "filters": filters}

    with patch("rag.coverage.precheck_question", return_value=expected) as precheck:
        result = precheck_coverage(query)

    precheck.assert_called_once_with(query)
    assert result == expected

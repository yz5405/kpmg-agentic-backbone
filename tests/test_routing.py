
"""Contract tests for agent.routing.determine_status (v0.2)."""

import pytest

from agent.routing import determine_status


@pytest.mark.parametrize(
    ("evidence", "error", "expected"),
    [
        (
            [{"text": "Revenue was $100 million",
              "metadata": {"source": "10-K"}}],
            None,
            "SUCCESS",
        ),
        ([], None, "NO_EVIDENCE"),
        ([], "Retriever unavailable", "ERROR"),
        (
            [{"text": "Partial evidence", "metadata": {}}],
            "Timeout",
            "ERROR",
        ),
    ],
    ids=[
        "success",
        "no_evidence",
        "error",
        "error_overrides_evidence",
    ],
)
def test_determine_status(evidence, error, expected):
    assert determine_status(
        evidence=evidence,
        error=error,
    ) == expected


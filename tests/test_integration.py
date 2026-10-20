"""Integration tests for the Agentic Backbone MVP.

Uses actual team modules with the bundled mock retriever.
Does not require the private RAG index or an API key.

Run:
    python -m pytest tests/test_integration.py -v
"""

import pytest

from agent.integration import run_integrated_agent


@pytest.fixture(autouse=True)
def use_mock_backend(monkeypatch):
    """Keep these tests independent of the real RAG index."""
    monkeypatch.setenv("KPMG_RAG_BACKEND", "mock")


QUESTION = (
    "What was Microsoft's total revenue "
    "for the three months ended March 31, 2026?"
)


def test_integrated_success():
    result = run_integrated_agent(QUESTION, top_k=8)

    assert result["status"] == "SUCCESS"
    assert result["error"] is None
    assert len(result["evidence"]) > 0

    assert result["filters"]["ticker"] == "MSFT"
    assert result["filters"]["fiscal_year"] == 2026
    assert result["filters"]["fiscal_period"] == "Q3"

    metadata = result["evidence"][0]["metadata"]
    assert metadata["ticker"] == "MSFT"
    assert metadata["source_url"]
    assert metadata["chunk_id"]


def test_integrated_no_evidence():
    result = run_integrated_agent(
        "What was Tesla's revenue in Q3 FY2026?",
        top_k=8,
    )

    assert result["status"] == "NO_EVIDENCE"
    assert result["evidence"] == []
    assert result["error"] is None


def test_integrated_error():
    result = run_integrated_agent(
        QUESTION,
        top_k=0,
    )

    assert result["status"] == "ERROR"
    assert result["error"] is not None


def test_integrated_logs():
    result = run_integrated_agent(QUESTION, top_k=8)

    assert result["logs"]
    assert all(
        entry.startswith(("[INFO]", "[WARNING]", "[ERROR]"))
        for entry in result["logs"]
    )

    assert any(
        "Workflow status: SUCCESS" in entry
        for entry in result["logs"]
    )

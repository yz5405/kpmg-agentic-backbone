
"""Automated tests for the LangGraph workflow v0.2.

These tests use deterministic mock dependencies.
No LLM API, external database, or real RAG service is required.

Run:
    python -m pytest tests/test_graph_workflow.py -v
"""

import pytest

from agent.graph_workflow import run_graph_agent


# ============================================================
# STEP 1 — Mock Functions
# ============================================================

def mock_parser(query: str) -> dict:
    """Extract mock financial filters."""

    if "Microsoft" in query:
        return {
            "ticker": "MSFT",
            "fiscal_year": 2026 if "2026" in query else 2025,
            "fiscal_period": "Q3" if "Q3" in query else None,
        }

    return {
        "ticker": None,
        "fiscal_year": None,
        "fiscal_period": None,
    }


def mock_retriever(
    query: str,
    filters: dict | None = None,
    top_k: int = 10,
) -> list[dict]:
    """Return deterministic mock evidence."""

    if top_k <= 0:
        raise ValueError("top_k must be greater than zero")

    if filters and filters.get("fiscal_year") == 2026:
        return [
            {
                "text": "Mock Microsoft Q3 FY2026 revenue evidence.",
                "metadata": {
                    "ticker": "MSFT",
                    "source": "10-Q",
                    "chunk_id": "mock-001",
                },
            }
        ]

    return []


# ============================================================
# STEP 2 — SUCCESS Test
# ============================================================

def test_graph_success():
    """Verify successful retrieval and metadata preservation."""

    result = run_graph_agent(
        query="Microsoft Q3 FY2026",
        top_k=10,
        parser=mock_parser,
        retriever=mock_retriever,
    )

    assert result["status"] == "SUCCESS"
    assert result["error"] is None

    assert result["filters"] == {
        "ticker": "MSFT",
        "fiscal_year": 2026,
        "fiscal_period": "Q3",
    }

    assert len(result["evidence"]) == 1

    evidence = result["evidence"][0]

    assert evidence["metadata"]["ticker"] == "MSFT"
    assert evidence["metadata"]["source"] == "10-Q"
    assert evidence["metadata"]["chunk_id"] == "mock-001"

    assert any(
        "RAG retrieval completed" in log
        for log in result["logs"]
    )

    assert result["logs"][-1] == (
        "[INFO] Workflow status: SUCCESS"
    )


# ============================================================
# STEP 3 — NO_EVIDENCE Test
# ============================================================

def test_graph_no_evidence():
    """Verify empty retrieval results are handled correctly."""

    result = run_graph_agent(
        query="Microsoft FY2025",
        top_k=10,
        parser=mock_parser,
        retriever=mock_retriever,
    )

    assert result["status"] == "NO_EVIDENCE"
    assert result["evidence"] == []
    assert result["error"] is None

    assert result["filters"]["ticker"] == "MSFT"
    assert result["filters"]["fiscal_year"] == 2025

    assert result["logs"][-1] == (
        "[INFO] Workflow status: NO_EVIDENCE"
    )


# ============================================================
# STEP 4 — ERROR Test
# ============================================================

def test_graph_invalid_top_k():
    """Verify invalid parameters enter the ERROR path."""

    result = run_graph_agent(
        query="Microsoft Q3 FY2026",
        top_k=0,
        parser=mock_parser,
        retriever=mock_retriever,
    )

    assert result["status"] == "ERROR"
    assert result["evidence"] == []

    assert result["error"] is not None
    assert "top_k must be greater than zero" in result["error"]

    assert any(
        "[ERROR] RAG retrieval failed" in log
        for log in result["logs"]
    )


# ============================================================
# STEP 5 — Additional Error Handling Tests
# ============================================================

def test_graph_parser_error_skips_retrieval():
    """A parser failure should skip the retrieval node."""

    def failing_parser(query):
        raise ValueError("Invalid query")

    def retriever_must_not_run(**kwargs):
        raise AssertionError("Retriever should not be called")

    result = run_graph_agent(
        query="Invalid question",
        parser=failing_parser,
        retriever=retriever_must_not_run,
    )

    assert result["status"] == "ERROR"
    assert result["error"] == "Invalid query"

    assert not any(
        "RAG retrieval started" in log
        for log in result["logs"]
    )


def test_graph_retriever_error():
    """A retriever exception should produce ERROR."""

    def failing_retriever(query, filters=None, top_k=10):
        raise RuntimeError("Retriever unavailable")

    result = run_graph_agent(
        query="Microsoft Q3 FY2026",
        parser=mock_parser,
        retriever=failing_retriever,
    )

    assert result["status"] == "ERROR"
    assert result["error"] == "Retriever unavailable"


def test_graph_state_isolation():
    """Two workflow executions must have independent state."""

    first = run_graph_agent(
        query="Microsoft Q3 FY2026",
        parser=mock_parser,
        retriever=mock_retriever,
    )

    second = run_graph_agent(
        query="Microsoft FY2025",
        parser=mock_parser,
        retriever=mock_retriever,
    )

    assert first["status"] == "SUCCESS"
    assert second["status"] == "NO_EVIDENCE"

    first["logs"].append("Only in first execution")

    assert "Only in first execution" not in second["logs"]

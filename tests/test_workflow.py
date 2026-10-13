
"""Integration tests for the KPMG Agentic Backbone workflow.

Uses deterministic mock dependencies to test LangChain
orchestration without an LLM API or real SEC database.

Run from repository root:
    python -m pytest tests/test_workflow.py -v
"""

import pytest

from agent.workflow import run_agent
from agent.state import AgentState, SUCCESS, NO_EVIDENCE, ERROR


# --------------------------------------------------
# Mock Query Parser — Member 1
# --------------------------------------------------

def mock_parser(query: str) -> dict:
    """Simulate financial filter extraction."""
    query_lower = query.lower()

    return {
        "ticker": "MSFT" if "microsoft" in query_lower else None,
        "fiscal_year": (
            2026 if "2026" in query_lower
            else 2025 if "2025" in query_lower
            else None
        ),
        "fiscal_period": "Q3" if "q3" in query_lower else None,
    }


# --------------------------------------------------
# Mock RAG Retriever — Member 2
# --------------------------------------------------

def mock_retriever(
    query: str,
    filters: dict | None = None,
    top_k: int = 10,
) -> list[dict]:
    """Return deterministic mock financial evidence."""

    if top_k <= 0:
        raise ValueError("top_k must be greater than zero")

    filters = filters or {}

    if (
        filters.get("ticker") == "MSFT"
        and filters.get("fiscal_year") == 2026
        and filters.get("fiscal_period") == "Q3"
    ):
        return [
            {
                "text": "Microsoft Q3 FY2026 revenue evidence",
                "metadata": {
                    "ticker": "MSFT",
                    "fiscal_year": 2026,
                    "fiscal_period": "Q3",
                    "source": "10-Q",
                },
            }
        ]

    return []


# --------------------------------------------------
# Mock Router — Member 3
# --------------------------------------------------

def mock_router(state: AgentState) -> AgentState:
    """Apply the agreed conditional routing rules."""

    if state.error is not None:
        state.status = ERROR
    elif state.evidence:
        state.status = SUCCESS
    else:
        state.status = NO_EVIDENCE

    return state


# --------------------------------------------------
# Mock Logger — Member 4
# --------------------------------------------------

def mock_logger(
    state: AgentState,
    message: str,
    level: str = "INFO",
) -> None:
    """Record an execution event."""

    state.logs.append(f"[{level}] {message}")


# --------------------------------------------------
# Shared pytest fixture
# --------------------------------------------------

@pytest.fixture
def mock_dependencies():
    """Provide the same mock components to every test."""

    return {
        "parser": mock_parser,
        "retriever": mock_retriever,
        "router": mock_router,
        "logger": mock_logger,
    }


# --------------------------------------------------
# Test 1 — SUCCESS
# --------------------------------------------------

def test_success(mock_dependencies):
    """Verify successful evidence retrieval and metadata."""

    state = run_agent(
        query="Microsoft Q3 FY2026",
        top_k=10,
        **mock_dependencies,
    )

    assert state.status == SUCCESS
    assert state.error is None

    assert state.filters == {
        "ticker": "MSFT",
        "fiscal_year": 2026,
        "fiscal_period": "Q3",
    }

    assert len(state.evidence) == 1
    assert state.evidence[0]["metadata"]["source"] == "10-Q"

    assert "[INFO] Workflow status: SUCCESS" in state.logs


# --------------------------------------------------
# Test 2 — NO_EVIDENCE
# --------------------------------------------------

def test_no_evidence(mock_dependencies):
    """Verify empty retrieval is not treated as an error."""

    state = run_agent(
        query="Microsoft FY2025",
        top_k=10,
        **mock_dependencies,
    )

    assert state.status == NO_EVIDENCE
    assert state.evidence == []
    assert state.error is None

    assert "[INFO] Workflow status: NO_EVIDENCE" in state.logs


# --------------------------------------------------
# Test 3 — ERROR
# --------------------------------------------------

def test_invalid_top_k(mock_dependencies):
    """Verify invalid retrieval input follows ERROR routing."""

    state = run_agent(
        query="Microsoft Q3 FY2026",
        top_k=0,
        **mock_dependencies,
    )

    assert state.status == ERROR
    assert state.evidence == []
    assert state.error == "top_k must be greater than zero"

    assert any(
        log.startswith("[ERROR] Workflow error:")
        for log in state.logs
    )

    assert "[INFO] Workflow status: ERROR" in state.logs

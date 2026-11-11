
"""Shared state for the LangGraph workflow (v0.2)."""

from typing import Any, Literal, TypedDict


class AgentGraphState(TypedDict):
    """State shared across LangGraph nodes."""

    query: str
    filters: dict[str, Any]
    top_k: int
    evidence: list[dict[str, Any]]
    evidence_status: Literal["ok", "weak", "empty"] | None
    weak_reasons: list[str]
    should_try_graphrag: bool
    graphrag_evidence: list[dict[str, Any]]
    graphrag_error: str | None
    status: str
    error: str | None
    logs: list[str]


def create_graph_state(
    query: str,
    top_k: int = 10
) -> AgentGraphState:
    """Create a fresh state for each workflow execution."""

    return {
        "query": query,
        "filters": {},
        "top_k": top_k,
        "evidence": [],
        "evidence_status": None,
        "weak_reasons": [],
        "should_try_graphrag": False,
        "graphrag_evidence": [],
        "graphrag_error": None,
        "status": "PENDING",
        "error": None,
        "logs": []
    }

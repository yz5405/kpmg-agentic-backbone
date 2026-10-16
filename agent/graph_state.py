
"""Shared state for the LangGraph workflow (v0.2)."""

from typing import Any, TypedDict


class AgentGraphState(TypedDict):
    """State shared across LangGraph nodes."""

    query: str
    filters: dict[str, Any]
    top_k: int
    evidence: list[dict[str, Any]]
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
        "status": "PENDING",
        "error": None,
        "logs": []
    }

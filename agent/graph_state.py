
"""Shared state for the LangGraph workflow (v0.2)."""

from typing import Any, Literal, TypedDict


class AgentGraphState(TypedDict):
    """State shared across LangGraph nodes."""

    company: str | None
    joint_trace: dict
    query_understanding_ms: float
    answer_ms: float
    selected_tool: str
    used_tool: str | None
    retrieval_attempts: list[dict]
    retrieval_failure: dict | None
    retrieval_limitation: str | None
    query: str
    filters: dict[str, Any]
    top_k: int
    form: str | None
    question_type: str | None
    query_understanding_mode: str | None
    evidence: list[dict[str, Any]]
    evidence_status: Literal["ok", "weak", "empty"] | None
    weak_reasons: list[str]
    should_try_graphrag: bool
    graphrag_evidence: list[dict[str, Any]]
    graphrag_error: str | None
    status: str
    error: str | None
    logs: list[str]
    answer: str | None
    citations: list[dict[str, Any]]
    model: str | None
    llm_calls: int
    token_usage: dict[str, int] | None


def create_graph_state(
    query: str,
    top_k: int = 15
) -> AgentGraphState:
    """Create a fresh state for each workflow execution."""

    return {
        "query": query,
        "filters": {},
        "top_k": top_k,
        "form": None,
        "question_type": None,
        "query_understanding_mode": None,
        "evidence": [],
        "evidence_status": None,
        "weak_reasons": [],
        "should_try_graphrag": False,
        "graphrag_evidence": [],
        "graphrag_error": None,
        "status": "PENDING",
        "error": None,
        "answer": None,
        "citations": [],
        "model": None,
        "llm_calls": 0,
        "token_usage": None,
        "logs": []
    }

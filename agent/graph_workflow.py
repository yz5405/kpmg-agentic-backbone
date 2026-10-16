
"""LangGraph workflow for the KPMG Agentic Backbone v0.2.

MVP:
    Query Parsing -> RAG Retrieval -> Conditional Routing

Supports mock dependencies until team modules are ready.
No LLM API key is required.
"""

from typing import Callable

from langgraph.graph import StateGraph, START, END

from agent.graph_state import (
    AgentGraphState,
    create_graph_state,
)


def build_graph(
    parser: Callable,
    retriever: Callable,
    router: Callable | None = None,
):
    """Build and compile the LangGraph workflow."""

    def add_logs(state, *messages):
        """Return an updated log list without mutating state."""
        return state["logs"] + list(messages)

    # NODE 1: Query Understanding
    def query_node(state: AgentGraphState) -> dict:
        try:
            filters = parser(state["query"])

            return {
                "filters": filters,
                "logs": add_logs(
                    state,
                    "[INFO] Query parsing started",
                    "[INFO] Query parsing completed",
                ),
            }

        except Exception as exc:
            return {
                "error": str(exc),
                "status": "ERROR",
                "logs": add_logs(
                    state,
                    "[INFO] Query parsing started",
                    f"[ERROR] Query parsing failed: {exc}",
                ),
            }

    # NODE 2: RAG Retrieval
    def retrieval_node(state: AgentGraphState) -> dict:
        try:
            if state["top_k"] <= 0:
                raise ValueError("top_k must be greater than zero")

            evidence = retriever(
                query=state["query"],
                filters=state["filters"],
                top_k=state["top_k"],
            )

            return {
                "evidence": evidence,
                "logs": add_logs(
                    state,
                    "[INFO] RAG retrieval started",
                    "[INFO] RAG retrieval completed",
                ),
            }

        except Exception as exc:
            return {
                "error": str(exc),
                "status": "ERROR",
                "logs": add_logs(
                    state,
                    "[INFO] RAG retrieval started",
                    f"[ERROR] RAG retrieval failed: {exc}",
                ),
            }

    # NODE 3: Conditional Routing
    def routing_node(state: AgentGraphState) -> dict:
        try:
            if router is not None:
                status = router(
                    evidence=state["evidence"],
                    error=state["error"],
                )
            elif state["error"] is not None:
                status = "ERROR"
            elif state["evidence"]:
                status = "SUCCESS"
            else:
                status = "NO_EVIDENCE"

            if status not in {"SUCCESS", "NO_EVIDENCE", "ERROR"}:
                raise ValueError("Unsupported routing status")

            return {
                "status": status,
                "logs": add_logs(
                    state,
                    f"[INFO] Workflow status: {status}",
                ),
            }

        except Exception as exc:
            return {
                "status": "ERROR",
                "error": str(exc),
                "logs": add_logs(
                    state,
                    f"[ERROR] Routing failed: {exc}",
                ),
            }

    # CONDITIONAL EDGE
    def after_query(state: AgentGraphState) -> str:
        """Skip retrieval if query parsing has failed."""
        if state["error"] is not None:
            return "routing"
        return "retrieval"

    def select_outcome(state: AgentGraphState) -> str:
        """Return the workflow's final routing outcome."""
        return state["status"]

    # BUILD STATEGRAPH
    graph = StateGraph(AgentGraphState)

    graph.add_node("query", query_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("routing", routing_node)

    graph.add_edge(START, "query")

    graph.add_conditional_edges(
        "query",
        after_query,
        {
            "retrieval": "retrieval",
            "routing": "routing",
        },
    )

    graph.add_edge("retrieval", "routing")

    graph.add_conditional_edges(
        "routing",
        select_outcome,
        {
            "SUCCESS": END,
            "NO_EVIDENCE": END,
            "ERROR": END,
        },
    )

    return graph.compile()


def run_graph_agent(
    query: str,
    top_k: int = 10,
    *,
    parser: Callable,
    retriever: Callable,
    router: Callable | None = None,
) -> AgentGraphState:
    """Execute the workflow with injected module functions."""

    graph = build_graph(
        parser=parser,
        retriever=retriever,
        router=router,
    )

    initial_state = create_graph_state(
        query=query,
        top_k=top_k,
    )

    initial_state["logs"].append("[INFO] Workflow started")

    return graph.invoke(initial_state)

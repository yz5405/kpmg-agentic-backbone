
"""LangGraph workflow for the KPMG Agentic Backbone v0.2.

MVP:
    Query Parsing -> RAG Retrieval -> Conditional Routing

Supports mock dependencies until team modules are ready.
No LLM API key is required.
"""

from typing import Callable
from time import perf_counter

from langgraph.graph import StateGraph, START, END

from agent.graph_state import (
    AgentGraphState,
    create_graph_state,
)
from agent.tool_selection import describe_retrieval_error, run_tool_selection
from agent.routing import EvidenceEvaluator, determine_status, should_try_graphrag


def build_graph(
    parser: Callable,
    retriever: Callable,
    router: Callable | None = None,
    *,
    graphrag_retriever: Callable | None = None,
    evidence_evaluator: EvidenceEvaluator | None = None,
    answer_generator: Callable | None = None,
    tools: dict[str, Callable] | None = None,
    trace_id: str | None = None,
    fallback_tool: str = "graphrag",
    joint_retrieval: Callable | None = None,
):
    """Build and compile the LangGraph workflow."""

    def add_logs(state, *messages):
        """Return an updated log list without mutating state."""
        return state["logs"] + list(messages)

    # NODE 1: Query Understanding
    def query_node(state: AgentGraphState) -> dict:
        try:
            started = perf_counter()
            parsed = parser(state["query"])
            filters = {
                key: parsed.get(key)
                for key in ("ticker", "fiscal_year", "fiscal_period")
                if parsed.get(key) is not None
            }

            tickers = parsed.get("tickers") or []
            if len(tickers) > 1:
                filters["ticker"] = tickers
            elif tickers and "ticker" not in filters:
                filters["ticker"] = tickers[0]

            return {
                "filters": filters,
                "company": parsed.get("company"),
                "query_understanding_ms": round((perf_counter() - started) * 1000, 2),
                "form": parsed.get("form"),
                "question_type": parsed.get("question_type"),
                "query_understanding_mode": parsed.get("query_understanding_mode"),
            "logs": add_logs(
                    state,
                    "[INFO] Query parsing started",
                    "[INFO] Query parsing completed",
                ),
            }

        except Exception:
            return {
                "error": "Query parsing failed.",
                "status": "ERROR",
                "logs": add_logs(
                    state,
                    "[INFO] Query parsing started",
                    "[ERROR] Query parsing failed",
                ),
            }

    # NODE 2: RAG Retrieval
    def retrieval_node(state: AgentGraphState) -> dict:
        if joint_retrieval is not None:
            return joint_retrieval(state)
        if tools is not None:
            return run_tool_selection(state, tools, trace_id)
        if state["top_k"] <= 0:
            return {
                "error": "top_k must be greater than zero",
                "status": "ERROR",
                "logs": add_logs(state, "[ERROR] RAG retrieval failed: invalid_request"),
            }
        try:
            result = retriever(
                query=state["query"],
                filters=state["filters"],
                top_k=state["top_k"],
            )

            if isinstance(result, list):
                retrieval_update = {"evidence": result}
            else:
                retrieval_update = {
                    "evidence": result["evidence"],
                    "evidence_status": result["evidence_status"],
                    "weak_reasons": result["weak_reasons"],
                }

            rows = retrieval_update["evidence"]
            return {
                **retrieval_update,
                "used_tool": "vector" if rows else None,
                "retrieval_attempts": [{
                    "tool": "vector", "outcome": "returned" if rows else "no_match",
                    "returned_count": len(rows),
                }],
                "logs": add_logs(
                    state,
                    "[INFO] RAG retrieval started",
                    "[INFO] RAG retrieval completed",
                ),
            }

        except Exception as exc:
            failure = describe_retrieval_error(exc)
            return {
                "error": failure["reason"],
                "retrieval_failure": failure,
                "retrieval_attempts": [{"tool": "vector", "outcome": "failed", "failure": failure}],
                "status": "ERROR",
                "logs": add_logs(
                    state,
                    "[INFO] RAG retrieval started",
                    f"[ERROR] RAG retrieval failed: {failure['type']}",
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
                "should_try_graphrag": should_try_graphrag(
                    evidence_status=state["evidence_status"],
                    workflow_status=status,
                ),
                "logs": add_logs(
                    state,
                    f"[INFO] Workflow status: {status}",
                ),
            }

        except Exception:
            return {
                "status": "ERROR",
                "error": "Routing failed.",
                "logs": add_logs(
                    state,
                    "[ERROR] Routing failed",
                ),
            }

    def graphrag_node(state: AgentGraphState) -> dict:
        """Collect GraphRAG evidence separately for Agent evaluation."""
        try:
            evidence = graphrag_retriever(
                query=state["query"],
                filters=state["filters"],
                top_k=state["top_k"],
            )
        except Exception as exc:
            failure = describe_retrieval_error(exc)
            return {
                "graphrag_error": failure["reason"],
                "retrieval_failure": failure,
                "retrieval_attempts": state["retrieval_attempts"] + [{
                    "tool": fallback_tool, "outcome": "failed", "failure": failure,
                }],
                "logs": add_logs(state, f"[WARNING] GraphRAG fallback failed: {failure['type']}"),
            }

        return {
            "graphrag_evidence": evidence,
            "retrieval_attempts": state["retrieval_attempts"] + [{
                "tool": fallback_tool, "outcome": "returned" if evidence else "no_match",
                "returned_count": len(evidence),
            }],
            "logs": add_logs(state, "[INFO] GraphRAG fallback completed"),
        }

    def evaluate_evidence_node(state: AgentGraphState) -> dict:
        """Finalize the response using the Agent's evidence judgment."""
        try:
            evidence = evidence_evaluator(
                query=state["query"],
                rag_evidence=state["evidence"],
                graphrag_evidence=state["graphrag_evidence"],
                evidence_status=state["evidence_status"],
                weak_reasons=state["weak_reasons"],
            )
            if not isinstance(evidence, list):
                raise TypeError("Evidence evaluator must return an evidence list")
        except Exception:
            return {
                "status": "ERROR",
                "error": "Evidence evaluation failed.",
                "logs": add_logs(state, "[ERROR] Evidence evaluation failed"),
            }

        if not evidence and state.get("retrieval_failure"):
            return {
                "evidence": [], "used_tool": None, "status": "ERROR",
                "error": state["retrieval_failure"]["reason"],
            }
        status = determine_status(evidence=evidence, error=None)
        if not evidence and state["evidence"] and graphrag_retriever is not None and not state["should_try_graphrag"]:
            return {
                "status": status,
                "should_try_graphrag": True,
                "logs": add_logs(state, "[INFO] Evidence evaluation requested GraphRAG fallback"),
            }
        used_tool = None
        if evidence:
            used_tool = fallback_tool if any(item in state["graphrag_evidence"] for item in evidence) else "vector"
        return {
            "evidence": evidence,
            "used_tool": used_tool,
            "status": status,
            "logs": add_logs(state, f"[INFO] Evidence evaluation status: {status}"),
        }

    # CONDITIONAL EDGE
    def after_query(state: AgentGraphState) -> str:
        """Skip retrieval if query parsing has failed."""
        if state["error"] is not None:
            return "routing"
        return "retrieval"

    def after_evaluation(state: AgentGraphState) -> str:
        if state["status"] == "NO_EVIDENCE" and state["should_try_graphrag"] and state["evidence"]:
            return "graphrag"
        return "finish"

    def select_outcome(state: AgentGraphState) -> str:
        """Run GraphRAG when the router requests it and a retriever is available."""
        if state["should_try_graphrag"] and graphrag_retriever is not None:
            return "graphrag"
        if evidence_evaluator is not None and state["status"] != "ERROR":
            return "evaluate_evidence"
        return state["status"]

    # Generation always follows the final evidence decision.
    if answer_generator is not None and graphrag_retriever is not None and evidence_evaluator is None:
        raise ValueError("Answer generation with GraphRAG requires an evidence evaluator")

    def answer_node(state: AgentGraphState) -> dict:
        if state.get("selected_tool") in {"direct_reply", "clarification"}:
            return {}
        started = perf_counter()
        update = answer_generator(state)
        update["answer_ms"] = round((perf_counter() - started) * 1000, 2)
        return {**update, "logs": add_logs(state, "[INFO] Answer generation completed")}

    # BUILD STATEGRAPH
    graph = StateGraph(AgentGraphState)

    terminal = "generate_answer" if answer_generator is not None else END
    if answer_generator is not None:
        graph.add_node("generate_answer", answer_node)
        graph.add_edge("generate_answer", END)

    graph.add_node("query", query_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("routing", routing_node)
    graph.add_node("graphrag", graphrag_node)
    outcomes = {
        "graphrag": "graphrag",
        "SUCCESS": terminal,
        "NO_EVIDENCE": terminal,
        "ERROR": terminal,
    }
    if evidence_evaluator is None:
        graph.add_edge("graphrag", terminal)
    else:
        graph.add_node("evaluate_evidence", evaluate_evidence_node)
        graph.add_edge("graphrag", "evaluate_evidence")
        graph.add_conditional_edges(
            "evaluate_evidence", after_evaluation, {"graphrag": "graphrag", "finish": terminal}
        )
        outcomes["evaluate_evidence"] = "evaluate_evidence"

    graph.add_edge(START, "query")

    graph.add_conditional_edges(
        "query",
        after_query,
        {
            "retrieval": "retrieval",
            "routing": "routing",
        },
    )

    graph.add_edge("retrieval", terminal if tools is not None or joint_retrieval is not None else "routing")

    graph.add_conditional_edges(
        "routing",
        select_outcome,
        outcomes,
    )

    return graph.compile()


def run_graph_agent(
    query: str,
    top_k: int = 15,
    *,
    parser: Callable,
    retriever: Callable,
    router: Callable | None = None,
    graphrag_retriever: Callable | None = None,
    evidence_evaluator: EvidenceEvaluator | None = None,
    answer_generator: Callable | None = None,
    tools: dict[str, Callable] | None = None,
    trace_id: str | None = None,
    fallback_tool: str = "graphrag",
    joint_retrieval: Callable | None = None,
) -> AgentGraphState:
    """Execute the workflow with injected module functions."""

    graph = build_graph(
        parser=parser,
        retriever=retriever,
        router=router,
        graphrag_retriever=graphrag_retriever,
        evidence_evaluator=evidence_evaluator,
        answer_generator=answer_generator,
        tools=tools,
        trace_id=trace_id,
        fallback_tool=fallback_tool,
        joint_retrieval=joint_retrieval,
    )

    initial_state = create_graph_state(
        query=query,
        top_k=top_k,
    )

    initial_state["logs"].append("[INFO] Workflow started")

    return graph.invoke(initial_state)

"""Integration entry point for the KPMG Agentic Backbone MVP.

Connects the team's actual modules to the LangGraph workflow.

Query Understanding -> RAG Retrieval -> Conditional Routing
-> Evidence, Metadata, Status, and Execution Logs

No LLM API key required.
"""

from agent.graph_workflow import run_graph_agent
from agent.query_parser import understand_query
from agent.tools.rag_tool import retrieve_evidence
from agent.routing import determine_status
from agent.logging_utils import format_log_event


def run_unified_agent(query: str, top_k: int = 8, *, strategy="routed", trace_id=None):
    """Run the unified workflow; model use is explicit and never silently falls back."""
    import os
    from agent.orchestrator import run_orchestrator, rule_plan
    from agent.tools.graphrag_adapter import graph_search, structured_search
    planner, generator = rule_plan, None
    mode = os.getenv("KPMG_MODEL_BACKEND", "offline")
    if mode == "openai":
        from agent.model import OpenAIModel
        model = OpenAIModel()
        planner, generator = model.plan, model.answer
    elif mode != "offline":
        raise ValueError("KPMG_MODEL_BACKEND must be offline or openai")
    return run_orchestrator(query, top_k, tools={"rag": retrieve_evidence,
        "graph_search": graph_search, "structured_search": structured_search},
        planner=planner, generator=generator, strategy=strategy, trace_id=trace_id)


def run_integrated_agent(
    query: str,
    top_k: int = 8,
) -> dict:
    """Run the integrated Agentic Backbone workflow.

    The retrieval backend is selected through KPMG_RAG_BACKEND:
        mock (default): bundled mock retriever
        real: RAG Team's retrieve() with RAG_INDEX_DIR configured
    """

    # Run LangGraph with actual team implementations.
    result = run_graph_agent(
        query=query,
        top_k=top_k,
        parser=understand_query,
        retriever=retrieve_evidence,
        router=determine_status,
    )

    # Normalize logs through the team's logging utility.
    # Existing workflow logs have the format "[LEVEL] message".
    normalized_logs = []

    for entry in result["logs"]:
        if entry.startswith("[INFO] "):
            normalized_logs.append(
                format_log_event(entry[7:], level="INFO")
            )
        elif entry.startswith("[WARNING] "):
            normalized_logs.append(
                format_log_event(entry[10:], level="WARNING")
            )
        elif entry.startswith("[ERROR] "):
            normalized_logs.append(
                format_log_event(entry[8:], level="ERROR")
            )
        else:
            normalized_logs.append(
                format_log_event(entry, level="INFO")
            )

    return {
        **result,
        "logs": normalized_logs,
    }


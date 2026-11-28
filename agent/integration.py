"""Integration entry point for the KPMG Agentic Backbone MVP.

Connects the team's actual modules to the LangGraph workflow.

Query Understanding -> RAG Retrieval -> Conditional Routing
-> Evidence, Metadata, Status, and Execution Logs

No LLM API key required.
"""

import os
from functools import partial
from typing import Callable

from agent.graph_workflow import run_graph_agent
from agent.joint_retrieval import run_joint_retrieval
from agent.answer_node import answer_generator_from_env
from agent.llm_query_understanding import understand_query_llm
from agent.tools.rag_tool import retrieve_evidence_result
from agent.routing import EvidenceEvaluator, determine_status
from agent.logging_utils import format_log_event


def run_integrated_agent(
    query: str,
    top_k: int = 15,
    *,
    graphrag_retriever: Callable | None = None,
    evidence_evaluator: EvidenceEvaluator | None = None,
    answer_generator: Callable | None = None,
    tools: dict[str, Callable] | None = None,
    trace_id: str | None = None,
    fallback_tool: str = "graphrag",
) -> dict:
    """Run the integrated Agentic Backbone workflow.

    The retrieval backend is selected through KPMG_RAG_BACKEND:
        mock (default): bundled mock retriever
        real: RAG Team's retrieve() with RAG_INDEX_DIR configured
    """

    if answer_generator is None:
        answer_generator = answer_generator_from_env()

    joint_retrieval = None
    if os.getenv("KPMG_RAG_BACKEND") == "real" and os.getenv("KPMG_COVERAGE_PRECHECK", "0") == "1":
        joint_tools = tools
        if joint_tools is None and graphrag_retriever is not None:
            arm = fallback_tool
            if arm in {"graph", "structured"}:
                joint_tools = {arm: lambda query, filters, top_k, trace_id: graphrag_retriever(
                    query=query, filters=filters, top_k=top_k,
                )}
        joint_retrieval = partial(
            run_joint_retrieval, trace_id=trace_id, graph_enabled=os.getenv("KPMG_GRAPHRAG_ENABLED") == "1",
            tools=joint_tools,
        )

    # Run LangGraph with actual team implementations.
    result = run_graph_agent(
        query=query,
        top_k=top_k,
        parser=understand_query_llm,
        retriever=partial(retrieve_evidence_result, trace_id=trace_id) if trace_id else retrieve_evidence_result,
        router=determine_status,
        graphrag_retriever=graphrag_retriever,
        evidence_evaluator=evidence_evaluator,
        answer_generator=answer_generator,
        tools=tools,
        trace_id=trace_id,
        fallback_tool=fallback_tool,
        joint_retrieval=joint_retrieval,
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

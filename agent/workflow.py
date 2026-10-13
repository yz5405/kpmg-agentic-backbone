"""LangChain workflow for the KPMG Agentic Backbone MVP.

Architecture:
    Query Parsing -> RAG Retrieval -> Conditional Routing

Uses LangChain RunnableLambda and LCEL.
No LLM API key or real SEC database is required.
"""

from typing import Callable

from langchain_core.runnables import RunnableLambda

from agent.state import (
    AgentState,
    create_initial_state,
    ERROR,
)


def run_agent(
    query: str,
    top_k: int = 10,
    *,
    parser: Callable | None = None,
    retriever: Callable | None = None,
    router: Callable | None = None,
    logger: Callable | None = None,
) -> AgentState:
    """Execute the LangChain-based single-agent workflow.

    Dependencies can be injected for mock testing.
    Returns the final AgentState.
    """

    # STEP 1: Initialize shared state
    state = create_initial_state(query, top_k)

    # STEP 2: Resolve logging dependency
    if logger is None:
        try:
            from agent.logging_utils import log_event
            logger = log_event
        except ImportError:
            # Temporary fallback until Member 4 finishes.
            def logger(state, message, level="INFO"):
                state.logs.append(f"[{level}] {message}")

    def log(message: str, level: str = "INFO"):
        logger(state, message, level=level)

    # STEP 3: Define LangChain nodes

    def parse_node(state: AgentState) -> AgentState:
        """Run query understanding and update filters."""
        log("Query parsing started")

        state.filters = parser(state.query)

        log("Query parsing completed")
        return state

    def retrieval_node(state: AgentState) -> AgentState:
        """Call the RAG adapter and store evidence."""
        log("RAG retrieval started")

        state.evidence = retriever(
            query=state.query,
            filters=state.filters,
            top_k=state.top_k,
        )

        log("RAG retrieval completed")
        return state

    def routing_node(state: AgentState) -> AgentState:
        """Determine the final workflow status."""
        return router(state)

    # STEP 4: Execute parsing and retrieval
    try:
        log("Workflow started")

        # Load team modules only when not injected.
        if parser is None:
            from agent.query_parser import understand_query
            parser = understand_query

        if retriever is None:
            from agent.tools.rag_tool import retrieve_evidence
            retriever = retrieve_evidence

        # LangChain Expression Language (LCEL)
        processing_chain = (
            RunnableLambda(parse_node)
            | RunnableLambda(retrieval_node)
        )

        state = processing_chain.invoke(state)

    except Exception as exc:
        # Capture parsing/retrieval failures
        state.error = str(exc)
        state.status = ERROR
        log(f"Workflow error: {state.error}", "ERROR")

    # STEP 5: Conditional routing
    try:
        if router is None:
            from agent.routing import route_result
            router = route_result

        routing_chain = RunnableLambda(routing_node)
        state = routing_chain.invoke(state)

    except Exception as exc:
        state.error = str(exc)
        state.status = ERROR
        log(f"Routing error: {state.error}", "ERROR")

    # STEP 6: Final execution log
    log(f"Workflow status: {state.status}")

    return state

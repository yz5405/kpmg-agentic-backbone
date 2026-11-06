
"""Tests for RAG / GraphRAG tool routing."""

from agent.tool_router import (
    select_retrieval_tool,
    make_routed_retriever,
)
from agent.tools.graphrag_adapter import retrieve_graph_evidence
from agent.integration import run_integrated_agent


def test_revenue_question_routes_to_rag():
    """A basic financial question should use RAG."""
    query = "What was Microsoft's total revenue?"
    assert select_retrieval_tool(query) == "rag"


def test_relationship_question_routes_to_graphrag():
    """A relationship question should use GraphRAG."""
    query = "How is Azure related to Intelligent Cloud?"
    assert select_retrieval_tool(query) == "graphrag"


def test_routed_retriever_calls_correct_tool():
    """The router should call the selected retriever."""
    calls = []

    def fake_rag(*, query, filters, top_k):
        calls.append("rag")
        return [{"text": "RAG evidence"}]

    def fake_graphrag(*, query, filters, top_k):
        calls.append("graphrag")
        return [{"text": "GraphRAG evidence"}]

    retriever = make_routed_retriever(
        rag_retriever=fake_rag,
        graphrag_retriever=fake_graphrag,
    )

    retriever(
        query="What was Microsoft revenue?",
        filters={"ticker": "MSFT"},
        top_k=5,
    )

    retriever(
        query="How is Azure related to Intelligent Cloud?",
        filters={"ticker": "MSFT"},
        top_k=5,
    )

    assert calls == ["rag", "graphrag"]


def test_graphrag_mock_returns_evidence():
    """GraphRAG Mock should return evidence for MSFT."""
    evidence = retrieve_graph_evidence(
        query="How is Azure related to Intelligent Cloud?",
        filters={"ticker": "MSFT"},
        top_k=5,
    )

    assert len(evidence) > 0
    assert evidence[0]["metadata"]["retrieval_method"] == "graphrag_mock"


def test_graphrag_mock_no_evidence():
    """GraphRAG Mock should return no evidence for other tickers."""
    evidence = retrieve_graph_evidence(
        query="How is Azure related to Intelligent Cloud?",
        filters={"ticker": "AAPL"},
        top_k=5,
    )

    assert evidence == []


def test_end_to_end_graphrag_routing():
    """The integrated workflow should use GraphRAG Mock."""
    result = run_integrated_agent(
        "How is Microsoft MSFT Azure related to Intelligent Cloud?"
    )

    assert result["status"] == "SUCCESS"
    assert len(result["evidence"]) > 0
    assert (
        result["evidence"][0]["metadata"]["retrieval_method"]
        == "graphrag_mock"
    )

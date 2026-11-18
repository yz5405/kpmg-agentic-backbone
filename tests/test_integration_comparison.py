
"""Integration comparison tests for the KPMG Agentic Backbone."""

import pytest

from agent.integration import run_integrated_agent


@pytest.fixture(autouse=True)
def use_mock_backend(monkeypatch):
    """Use the bundled mock RAG backend."""
    monkeypatch.setenv("KPMG_RAG_BACKEND", "mock")


QUESTION = (
    "What was Microsoft's total revenue "
    "for the three months ended March 31, 2026?"
)


def test_integration_rag_only():
    """Case 1: Verify the integrated RAG-only workflow."""

    result = run_integrated_agent(
        query=QUESTION,
        top_k=8,
    )

    print("\n--- CASE 1: RAG ONLY ---")
    print("Test Mode: MOCK")
    print("Final Status:", result["status"])
    print("Evidence Count:", len(result["evidence"]))
    print("GraphRAG Evidence:", len(result["graphrag_evidence"]))
    print("Fallback Decision:", result["should_try_graphrag"])
    print("Error:", result["error"])

    assert result["status"] == "SUCCESS"
    assert result["error"] is None
    assert len(result["evidence"]) > 0
    assert result["graphrag_evidence"] == []

def test_integration_graphrag_fallback(monkeypatch):
    """Case 2: Empty RAG triggers GraphRAG through integration."""

    import agent.integration as integration

    tool_calls = []

    def mock_empty_rag(*, query, filters, top_k):
        tool_calls.append("RAG")
        return {
            "evidence": [],
            "evidence_status": "empty",
            "weak_reasons": ["no_results"],
        }

    def mock_graphrag(*, query, filters, top_k):
        tool_calls.append("GraphRAG")
        return [{
            "text": "Total revenue 70000",
            "metadata": {"ticker": "MSFT"},
        }]

    monkeypatch.setattr(
        integration,
        "retrieve_evidence_result",
        mock_empty_rag,
    )

    result = run_integrated_agent(
        query=QUESTION,
        top_k=8,
        graphrag_retriever=mock_graphrag,
    )

    print("\n--- CASE 2: GRAPHRAG FALLBACK ---")
    print("Test Mode: MOCK")
    print("Final Status:", result["status"])
    print("RAG Evidence Status:", result["evidence_status"])
    print("GraphRAG Evidence:", len(result["graphrag_evidence"]))
    print("Fallback Decision:", result["should_try_graphrag"])
    print("Tool Calls:", tool_calls)

    assert result["evidence_status"] == "empty"
    assert result["should_try_graphrag"] is True
    assert tool_calls == ["RAG", "GraphRAG"]
    assert len(result["graphrag_evidence"]) == 1
    assert result["error"] is None

def test_integration_graphrag_with_evaluator(monkeypatch):
    """Case 3: GraphRAG evidence is accepted by the evaluator."""

    import agent.integration as integration

    tool_calls = []

    def mock_empty_rag(*, query, filters, top_k):
        tool_calls.append("RAG")
        return {
            "evidence": [],
            "evidence_status": "empty",
            "weak_reasons": ["no_results"],
        }

    graph_evidence = {
        "text": "Total revenue 70000",
        "metadata": {"ticker": "MSFT"},
    }

    def mock_graphrag(*, query, filters, top_k):
        tool_calls.append("GraphRAG")
        return [graph_evidence]

    def mock_evaluator(
        *, query, rag_evidence, graphrag_evidence,
        evidence_status, weak_reasons
    ):
        tool_calls.append("Evaluator")
        return graphrag_evidence

    monkeypatch.setattr(
        integration,
        "retrieve_evidence_result",
        mock_empty_rag,
    )

    result = run_integrated_agent(
        query=QUESTION,
        top_k=8,
        graphrag_retriever=mock_graphrag,
        evidence_evaluator=mock_evaluator,
    )

    print("\n--- CASE 3: GRAPHRAG + EVALUATOR ---")
    print("Test Mode: MOCK")
    print("RAG Evidence Status:", result["evidence_status"])
    print("Final Status:", result["status"])
    print("GraphRAG Evidence:", len(result["graphrag_evidence"]))
    print("Accepted Evidence:", len(result["evidence"]))
    print("Fallback Decision:", result["should_try_graphrag"])
    print("Tool Calls:", tool_calls)

    assert result["evidence_status"] == "empty"
    assert result["should_try_graphrag"] is True
    assert result["status"] == "SUCCESS"
    assert result["evidence"] == [graph_evidence]
    assert result["error"] is None
    assert tool_calls == ["RAG", "GraphRAG", "Evaluator"]



def test_integration_graphrag_with_real_evaluator(monkeypatch):
    """Case 4: GraphRAG fallback with the real evidence evaluator."""
    import agent.integration as integration
    from agent.routing import evaluate_financial_evidence
    from agent.tools.rag_tool import retrieve_evidence_result

    retrieved = retrieve_evidence_result(QUESTION, top_k=8)

    accepted = evaluate_financial_evidence(
        query=QUESTION,
        rag_evidence=retrieved["evidence"],
        graphrag_evidence=[],
        evidence_status=retrieved["evidence_status"],
        weak_reasons=retrieved["weak_reasons"],
    )

    assert len(accepted) == 1

    tool_calls = []

    def mock_empty_rag(*, query, filters, top_k):
        tool_calls.append("RAG")
        return {
            "evidence": [],
            "evidence_status": "empty",
            "weak_reasons": ["no_results"],
        }

    def mock_graphrag(*, query, filters, top_k):
        tool_calls.append("GraphRAG")
        return accepted

    monkeypatch.setattr(
        integration, "retrieve_evidence_result", mock_empty_rag
    )

    result = run_integrated_agent(
        query=QUESTION,
        top_k=8,
        graphrag_retriever=mock_graphrag,
        evidence_evaluator=evaluate_financial_evidence,
    )

    print("\n--- CASE 4: GRAPHRAG + REAL EVALUATOR ---")
    print("RAG Evidence Status:", result["evidence_status"])
    print("GraphRAG Evidence:", len(result["graphrag_evidence"]))
    print("Accepted Evidence:", len(result["evidence"]))
    print("Fallback Decision:", result["should_try_graphrag"])
    print("Final Status:", result["status"])
    print("Tool Calls:", tool_calls)
    print("Error:", result["error"])

    assert result["evidence_status"] == "empty"
    assert result["should_try_graphrag"] is True
    assert len(result["graphrag_evidence"]) == 1
    assert len(result["evidence"]) == 1
    assert result["status"] == "SUCCESS"
    assert result["error"] is None
    assert tool_calls == ["RAG", "GraphRAG"]



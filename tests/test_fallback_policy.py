
"""Mock tests for Agent Evidence Sufficiency and GraphRAG fallback."""

from time import perf_counter

from agent.graph_workflow import run_graph_agent


def test_rag_empty_triggers_graphrag():
    """Case 1: Empty RAG should trigger GraphRAG fallback."""

    tool_calls = []

    query = "What was Microsoft's total revenue in Q3 FY2026?"

    mock_evidence = {
        "text": "Total revenue 70000",
        "metadata": {
            "ticker": "MSFT",
            "form": "10-Q",
            "fiscal_year": 2026,
            "fiscal_period": "Q3",
            "source_url": "https://www.sec.gov/mock",
        },
    }

    def mock_parser(query):
        return {"ticker": "MSFT"}

    def mock_rag_retriever(*, query, filters, top_k):
        tool_calls.append("RAG")
        return {
            "evidence": [],
            "evidence_status": "empty",
            "weak_reasons": ["no_results"],
        }

    def mock_graphrag_retriever(*, query, filters, top_k):
        tool_calls.append("GraphRAG")
        return [mock_evidence]

    def mock_evaluator(
        *, query, rag_evidence, graphrag_evidence,
        evidence_status, weak_reasons
    ):
        # Simplified evaluator for testing workflow routing only.
        return graphrag_evidence

    start = perf_counter()

    result = run_graph_agent(
        query=query,
        parser=mock_parser,
        retriever=mock_rag_retriever,
        graphrag_retriever=mock_graphrag_retriever,
        evidence_evaluator=mock_evaluator,
    )

    latency_ms = (perf_counter() - start) * 1000

    print("\n--- CASE 1: RAG EMPTY → GRAPHRAG ---")
    print("Test Mode: MOCK")
    print("Evidence Status:", result["evidence_status"])
    print("Final Status:", result["status"])
    print("Fallback Decision:", result["should_try_graphrag"])
    print("Evidence Sufficiency:", bool(result["evidence"]))
    print("Tool Calls:", tool_calls)
    print(f"Latency: {latency_ms:.2f} ms")

    assert result["evidence_status"] == "empty"
    assert result["should_try_graphrag"] is True
    assert tool_calls == ["RAG", "GraphRAG"]
    assert result["status"] == "SUCCESS"
    assert len(result["evidence"]) == 1

def test_rag_weak_triggers_graphrag():
    """Case 2: Weak RAG should trigger GraphRAG fallback."""

    tool_calls = []
    query = "What was Microsoft's total revenue in Q3 FY2026?"

    weak_evidence = {
        "text": "Microsoft reported revenue growth.",
        "metadata": {"ticker": "MSFT"},
    }

    graph_evidence = {
        "text": "Total revenue 70000",
        "metadata": {
            "ticker": "MSFT",
            "form": "10-Q",
            "fiscal_year": 2026,
            "fiscal_period": "Q3",
            "source_url": "https://www.sec.gov/mock",
        },
    }

    def mock_parser(query):
        return {"ticker": "MSFT"}

    def mock_rag_retriever(*, query, filters, top_k):
        tool_calls.append("RAG")
        return {
            "evidence": [weak_evidence],
            "evidence_status": "weak",
            "weak_reasons": ["missing_numeric_value"],
        }

    def mock_graphrag_retriever(*, query, filters, top_k):
        tool_calls.append("GraphRAG")
        return [graph_evidence]

    def mock_evaluator(
        *, query, rag_evidence, graphrag_evidence,
        evidence_status, weak_reasons
    ):
        # Only accept GraphRAG evidence for this mock test.
        return graphrag_evidence

    start = perf_counter()

    result = run_graph_agent(
        query=query,
        parser=mock_parser,
        retriever=mock_rag_retriever,
        graphrag_retriever=mock_graphrag_retriever,
        evidence_evaluator=mock_evaluator,
    )

    latency_ms = (perf_counter() - start) * 1000

    print("\n--- CASE 2: RAG WEAK → GRAPHRAG ---")
    print("Test Mode: MOCK")
    print("Evidence Status:", result["evidence_status"])
    print("Final Status:", result["status"])
    print("Fallback Decision:", result["should_try_graphrag"])
    print("Evidence Sufficiency:", bool(result["evidence"]))
    print("Tool Calls:", tool_calls)
    print(f"Latency: {latency_ms:.2f} ms")

    assert result["evidence_status"] == "weak"
    assert result["should_try_graphrag"] is True
    assert tool_calls == ["RAG", "GraphRAG"]
    assert result["status"] == "SUCCESS"
    assert result["evidence"] == [graph_evidence]

def test_rag_ok_but_agent_no_evidence():
    """Case 3: RAG says ok, but Agent rejects the evidence."""

    tool_calls = []
    query = "What was Microsoft's total revenue in Q3 FY2026?"

    insufficient_evidence = {
        "text": "Microsoft's revenue increased during the quarter.",
        "metadata": {
            "ticker": "MSFT",
            "source_url": "https://www.sec.gov/mock",
        },
    }

    def mock_parser(query):
        return {"ticker": "MSFT"}

    def mock_rag_retriever(*, query, filters, top_k):
        tool_calls.append("RAG")
        return {
            "evidence": [insufficient_evidence],
            "evidence_status": "ok",
            "weak_reasons": [],
        }

    def mock_graphrag_retriever(*, query, filters, top_k):
        tool_calls.append("GraphRAG")
        return [{
            "text": "Total revenue 70000",
            "metadata": {"ticker": "MSFT"},
        }]

    def mock_evaluator(
        *, query, rag_evidence, graphrag_evidence,
        evidence_status, weak_reasons
    ):
        # Reject evidence without a numerical revenue value.
        return [
            item for item in (*rag_evidence, *graphrag_evidence)
            if "Total revenue 70000" in item["text"]
        ]

    start = perf_counter()

    result = run_graph_agent(
        query=query,
        parser=mock_parser,
        retriever=mock_rag_retriever,
        graphrag_retriever=mock_graphrag_retriever,
        evidence_evaluator=mock_evaluator,
    )

    latency_ms = (perf_counter() - start) * 1000

    print("\n--- CASE 3: RAG OK BUT AGENT NO_EVIDENCE ---")
    print("Test Mode: MOCK")
    print("Evidence Status:", result["evidence_status"])
    print("Final Status:", result["status"])
    print("Fallback Decision:", result["should_try_graphrag"])
    print("Evidence Sufficiency:", bool(result["evidence"]))
    print("Tool Calls:", tool_calls)
    print(f"Latency: {latency_ms:.2f} ms")

    assert result["evidence_status"] == "ok"
    assert result["status"] == "NO_EVIDENCE"
    assert result["should_try_graphrag"] is False
    assert result["evidence"] == []
    assert tool_calls == ["RAG"]

def test_fallback_on_vs_off():
    """Case 4: Compare GraphRAG fallback enabled vs disabled."""

    query = "What was Microsoft's total revenue in Q3 FY2026?"
    results = {}

    for enabled in [False, True]:
        tool_calls = []

        def mock_parser(query):
            return {"ticker": "MSFT"}

        def mock_rag_retriever(*, query, filters, top_k):
            tool_calls.append("RAG")
            return {
                "evidence": [],
                "evidence_status": "empty",
                "weak_reasons": ["no_results"],
            }

        def mock_graphrag_retriever(*, query, filters, top_k):
            tool_calls.append("GraphRAG")
            return [{
                "text": "Total revenue 70000",
                "metadata": {"ticker": "MSFT"},
            }]

        def mock_evaluator(
            *, query, rag_evidence, graphrag_evidence,
            evidence_status, weak_reasons
        ):
            return graphrag_evidence

        start = perf_counter()

        result = run_graph_agent(
            query=query,
            parser=mock_parser,
            retriever=mock_rag_retriever,
            graphrag_retriever=(
                mock_graphrag_retriever if enabled else None
            ),
            evidence_evaluator=mock_evaluator,
        )

        latency_ms = (perf_counter() - start) * 1000

        results[enabled] = {
            "evidence_status": result["evidence_status"],
            "final_status": result["status"],
            "fallback_decision": result["should_try_graphrag"],
            "evidence_sufficient": bool(result["evidence"]),
            "tool_calls": tool_calls,
            "latency_ms": latency_ms,
        }

    print("\n--- CASE 4: FALLBACK ON VS OFF ---")
    print("Test Mode: MOCK")

    for enabled, data in results.items():
        print(f"\nFallback Enabled: {enabled}")
        for key, value in data.items():
            print(f"{key}: {value}")

    assert results[False]["final_status"] == "NO_EVIDENCE"
    assert results[True]["final_status"] == "SUCCESS"
    assert results[False]["tool_calls"] == ["RAG"]
    assert results[True]["tool_calls"] == ["RAG", "GraphRAG"]
    assert results[False]["evidence_sufficient"] is False
    assert results[True]["evidence_sufficient"] is True

def test_gsv0_msft_023_false_refusal():
    """Case 5: Mock reconciliation evidence should not trigger fallback."""

    tool_calls = []
    query = (
        "Reconcile Microsoft's change in cash and cash equivalents "
        "for the nine months ended March 31, 2026 using operating, "
        "financing, investing, and foreign-exchange cash flows. "
        "Then reconcile the ending cash balance to the balance sheet. "
        "Use USD millions."
    )

    mock_evidence = {
        "text": (
            "Mock reconciliation: operating cash flow + financing "
            "cash flow + investing cash flow + FX effect equals "
            "the change in cash. Beginning cash plus change "
            "equals ending cash on the balance sheet."
        ),
        "metadata": {
            "ticker": "MSFT",
            "form": "10-Q",
            "source_url": "https://www.sec.gov/mock",
        },
    }

    def mock_parser(query):
        return {"ticker": "MSFT"}

    def mock_rag_retriever(*, query, filters, top_k):
        tool_calls.append("RAG")
        return {
            "evidence": [mock_evidence],
            "evidence_status": "ok",
            "weak_reasons": [],
        }

    def mock_graphrag_retriever(*, query, filters, top_k):
        tool_calls.append("GraphRAG")
        return []

    def mock_evaluator(
        *, query, rag_evidence, graphrag_evidence,
        evidence_status, weak_reasons
    ):
        # Mock policy: accept the supplied reconciliation fixture.
        return rag_evidence

    start = perf_counter()

    result = run_graph_agent(
        query=query,
        parser=mock_parser,
        retriever=mock_rag_retriever,
        graphrag_retriever=mock_graphrag_retriever,
        evidence_evaluator=mock_evaluator,
    )

    latency_ms = (perf_counter() - start) * 1000

    print("\n--- CASE 5: GSV0-MSFT-023 ---")
    print("Test Mode: MOCK")
    print("Evidence Status:", result["evidence_status"])
    print("Final Status:", result["status"])
    print("Fallback Decision:", result["should_try_graphrag"])
    print("Evidence Sufficiency:", bool(result["evidence"]))
    print("Tool Calls:", tool_calls)
    print(f"Latency: {latency_ms:.2f} ms")

    assert result["status"] == "SUCCESS"
    assert result["should_try_graphrag"] is False
    assert tool_calls == ["RAG"]
    assert result["evidence"] == [mock_evidence]


def test_ev1r_005_false_premise():
    """Case 6: Mock premise correction should avoid false refusal."""

    tool_calls = []

    query = (
        "Since Microsoft acquired OpenAI, which of Microsoft's "
        "segments reports OpenAI's revenue?"
    )

    mock_evidence = {
        "text": (
            "The question contains a false premise. "
            "Microsoft has not acquired OpenAI, so OpenAI's "
            "revenue is not reported as revenue of a Microsoft segment."
        ),
        "metadata": {
            "ticker": "MSFT",
            "source_url": "https://www.sec.gov/mock",
        },
    }

    def mock_parser(query):
        return {"ticker": "MSFT"}

    def mock_rag_retriever(*, query, filters, top_k):
        tool_calls.append("RAG")
        return {
            "evidence": [mock_evidence],
            "evidence_status": "ok",
            "weak_reasons": [],
        }

    def mock_graphrag_retriever(*, query, filters, top_k):
        tool_calls.append("GraphRAG")
        return []

    def mock_evaluator(
        *, query, rag_evidence, graphrag_evidence,
        evidence_status, weak_reasons
    ):
        # Mock policy: accept evidence that corrects the premise.
        return rag_evidence

    start = perf_counter()

    result = run_graph_agent(
        query=query,
        parser=mock_parser,
        retriever=mock_rag_retriever,
        graphrag_retriever=mock_graphrag_retriever,
        evidence_evaluator=mock_evaluator,
    )

    latency_ms = (perf_counter() - start) * 1000

    print("\n--- CASE 6: EV1R-005 ---")
    print("Test Mode: MOCK")
    print("Evidence Status:", result["evidence_status"])
    print("Final Status:", result["status"])
    print("Fallback Decision:", result["should_try_graphrag"])
    print("Evidence Sufficiency:", bool(result["evidence"]))
    print("Tool Calls:", tool_calls)
    print(f"Latency: {latency_ms:.2f} ms")

    assert result["status"] == "SUCCESS"
    assert result["should_try_graphrag"] is False
    assert tool_calls == ["RAG"]
    assert result["evidence"] == [mock_evidence]

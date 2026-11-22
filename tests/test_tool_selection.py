from unittest.mock import Mock

import pytest

from agent.tool_selection import run_tool_selection, select_tool


def test_capability_aware_routes():
    assert select_tool("What was Microsoft's revenue in FY2026?", "metric_lookup",
                       {"ticker": "MSFT", "fiscal_year": 2026}) == ("structured", "financial")
    assert select_tool("Summarize the competition risk", None, {}) == ("vector", "narrative")
    assert select_tool("Find Microsoft claims about competition", "relationship", {}) == ("graph", "narrative")
    assert select_tool("What shared risks connect Microsoft and Apple?", "relationship", {}) == (
        "vector", "unsupported_relationship"
    )


@pytest.mark.parametrize("query", [
    # Eval Gold Set v2.2 intent from EV2-040, EV2-042, EV2-043, then a two-company control.
    "Among the ten companies in the corpus, which reported the highest revenue for its most recent fiscal year?",
    "Rank the ten companies by net margin (net income / revenue) for each company's most recent fiscal year.",
    "Which company had the fastest revenue growth in its most recent fiscal year versus the year before?",
    "Compare Microsoft's and Apple's revenue in FY2026.",
])
def test_unimplemented_calculations_abstain_with_retrieved_rows(query):
    state = request(query, filters={"ticker": ["MSFT", "AAPL"]})
    vector = Mock(return_value={"evidence": [ROW], "evidence_status": "ok"})
    result = run_tool_selection(state, {"vector": vector}, "rank")
    assert result["status"] == "NO_EVIDENCE"
    assert result["retrieval_limitation"]
    assert result["retrieval_attempts"][0]["outcome"] == "insufficient_evidence"
    assert vector.call_args.kwargs["filters"]["ticker"] == ["MSFT", "AAPL"]


ROW = {"text": "Reported competition risks.", "metadata": {
    "source_url": "https://www.sec.gov/Archives/edgar/data/789019/000119312526191507/msft.htm",
    "ticker": "MSFT", "form": "10-Q", "section_id": "s1",
    "fiscal_year": 2026, "fiscal_period": "Q3", "accession_number": "0001193125-26-191507",
}}


def request(query="Find Microsoft claims about competition", filters=None):
    return {"query": query, "question_type": None, "form": "10-Q",
            "filters": filters or {"ticker": "MSFT", "fiscal_year": 2026, "fiscal_period": "Q3"},
            "top_k": 10, "logs": []}


@pytest.mark.parametrize("key,value", [("ticker", "AAPL"), ("fiscal_year", 2025), ("fiscal_period", "Q2")])
def test_out_of_scope_rows_are_rejected(key, value):
    row = {**ROW, "metadata": {**ROW["metadata"], key: value}}
    result = run_tool_selection(request(), {"graph": Mock(return_value=[row]), "vector": Mock(return_value=[])}, "filters")
    assert result["status"] == "NO_EVIDENCE"
    assert len(result["retrieval_attempts"]) == 2


def test_backend_failure_does_not_masquerade_as_no_match():
    class RetrievalUnavailableError(RuntimeError):
        pass

    graph = Mock(side_effect=RetrievalUnavailableError("private configuration"))
    vector = Mock(return_value=[])
    result = run_tool_selection(request(), {"graph": graph, "vector": vector}, "error")
    assert result["status"] == "ERROR"
    assert result["retrieval_failure"]["type"] == "backend_unavailable"
    assert "private configuration" not in repr(result)
    assert graph.call_count == vector.call_count == 1


def test_failed_graph_can_fall_back_to_cited_vector_result():
    graph = Mock(side_effect=TimeoutError())
    vector = Mock(return_value={"evidence": [ROW], "evidence_status": "ok"})
    result = run_tool_selection(request(), {"graph": graph, "vector": vector}, "fallback")
    assert result["status"] == "SUCCESS"
    assert result["selected_tool"] == "graph" and result["used_tool"] == "vector"
    assert vector.call_args.kwargs["trace_id"] == "fallback"


def test_exact_quarter_fact_excludes_segment_and_year_to_date():
    from agent.routing import evaluate_financial_evidence

    metadata = {
        **ROW["metadata"], "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "period_start": "2026-01-01", "period_end": "2026-03-31", "dimensions": [],
        "unit_ref": "USD", "value_num": 100, "fact_id": "quarter",
    }
    matching = {"text": "Consolidated revenue: 100 USD", "metadata": metadata}
    segment = {**matching, "metadata": {**metadata, "dimensions": [{"member": "Segment A"}]}}
    ytd = {**matching, "metadata": {**metadata, "period_start": "2025-07-01"}}
    result = evaluate_financial_evidence(
        query="What was Microsoft's revenue in Q3 FY2026?", rag_evidence=[],
        graphrag_evidence=[segment, ytd, matching], evidence_status="ok", weak_reasons=[],
    )
    assert result == [matching]

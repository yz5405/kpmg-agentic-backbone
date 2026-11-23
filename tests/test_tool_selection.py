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
    "Which company had higher revenue in FY2026, Microsoft or Apple?",
    "Calculate the combined revenue for Microsoft and Apple in FY2026.",
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
    assert graph.call_count == 2 and vector.call_count == 1
    assert result["retrieval_attempts"][0]["retry_count"] == 1


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
    wrong_unit = {**matching, "text": "Consolidated revenue: 100 CAD"}
    result = evaluate_financial_evidence(
        query="What was Microsoft's revenue in Q3 FY2026?", rag_evidence=[],
        graphrag_evidence=[segment, ytd, wrong_unit, matching], evidence_status="ok", weak_reasons=[],
    )
    assert result == [matching]


@pytest.mark.parametrize("field", ["fiscal_year", "fiscal_period"])
def test_vector_does_not_reuse_evidence_without_requested_fiscal_label(field):
    metadata = {key: value for key, value in ROW["metadata"].items() if key != field}
    row = {**ROW, "metadata": metadata}
    vector = Mock(return_value={"evidence": [row], "evidence_status": "ok"})
    result = run_tool_selection(request("Summarize Microsoft's risks"), {"vector": vector}, "missing-label")
    assert result["status"] == "NO_EVIDENCE"
    assert result["retrieval_attempts"][0]["outcome"] == "insufficient_evidence"


def test_api_answer_configuration_failure_is_safe(monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import app

    monkeypatch.setenv("KPMG_ANSWER_ENABLED", "1")
    monkeypatch.setenv("KPMG_ANSWER_TIMEOUT", "private-invalid-setting")
    response = TestClient(app).post("/query", json={"query": "Microsoft's revenue in FY2026"})
    assert response.status_code == 503
    assert response.json() == {"detail": "Answer generation is not configured."}


def test_legacy_api_exposes_single_failed_attempt_without_secret(monkeypatch):
    from fastapi.testclient import TestClient

    import agent.integration
    import api.main

    monkeypatch.setenv("KPMG_GRAPHRAG_ENABLED", "1")
    monkeypatch.setenv("KPMG_TOOL_SELECTION", "legacy")
    monkeypatch.setenv("KPMG_GRAPHRAG_ARM", "structured")
    monkeypatch.setenv("KPMG_ANSWER_ENABLED", "0")
    monkeypatch.setenv("KPMG_QUERY_LLM_ENABLED", "0")
    calls = []

    def vector(**kwargs):
        calls.append(("vector", kwargs["trace_id"]))
        return {"evidence": [], "evidence_status": "empty", "weak_reasons": []}

    def structured(**kwargs):
        calls.append(("structured", kwargs["trace_id"]))
        raise ConnectionError("private connection string")

    monkeypatch.setattr(agent.integration, "retrieve_evidence_result", vector)
    monkeypatch.setattr(api.main, "retrieve_structured_evidence", structured)
    response = TestClient(api.main.app).post("/query", json={
        "query": "What was Microsoft's revenue in FY2026?", "trace_id": "legacy-smoke",
    })
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "ERROR"
    assert result["selected_tool"] == "vector"
    assert result["used_tool"] is None and result["fallback_attempts"] == 1
    assert not result["fallback_used"]
    assert calls == [("vector", "legacy-smoke"), ("structured", "legacy-smoke")]
    assert result["retrieval_attempts"][-1]["failure"]["type"] == "backend_unavailable"
    assert "private connection string" not in response.text


def test_graph_filter_error_does_not_retry_or_fall_back():
    class FilterNotSupportedError(ValueError):
        pass

    graph = Mock(side_effect=FilterNotSupportedError("not an available filter"))
    vector = Mock()
    result = run_tool_selection(request(), {"graph": graph, "vector": vector}, "unsupported")
    assert result["status"] == "ERROR"
    assert result["retrieval_failure"]["type"] == "unsupported_filter"
    assert result["retrieval_attempts"][0]["retry_count"] == 0
    graph.assert_called_once()
    vector.assert_not_called()


def test_graph_retries_once_then_uses_same_backend():
    class RetrievalUnavailableError(RuntimeError):
        pass

    graph = Mock(side_effect=[RetrievalUnavailableError("cold service"), [ROW]])
    vector = Mock()
    result = run_tool_selection(request(), {"graph": graph, "vector": vector}, "cold")
    assert result["used_tool"] == "graph"
    assert result["retrieval_attempts"][0]["retry_count"] == 1
    assert graph.call_count == 2
    vector.assert_not_called()


def test_subsidiary_requires_claim_and_location_without_vector_fallback():
    evidence = {**ROW, "text": "An unsupported claim about subsidiaries in Canada."}
    graph = Mock(return_value=[evidence])
    vector = Mock()
    state = request("Which subsidiaries does Microsoft have in Ireland?")
    result = run_tool_selection(state, {"graph": graph, "vector": vector}, "location")
    assert result["selected_tool"] == "graph" and result["status"] == "NO_EVIDENCE"
    vector.assert_not_called()


def test_structured_quarter_rejects_nine_month_and_nonconsolidated_inputs():
    from agent.routing import evaluate_structured_lookup

    metadata = {
        **ROW["metadata"], "ticker": "AAPL", "fact_id": "fact", "form": "10-Q",
        "concept": "us-gaap:NetIncomeLoss", "period_start": "2026-03-29", "period_end": "2026-06-27",
        "dimensions": [], "value_num": 100,
    }
    valid = {"text": "us-gaap:NetIncomeLoss: 100 USD", "metadata": metadata}
    cases = [
        valid,
        {**valid, "metadata": {**metadata, "period_start": "2025-09-28"}},
        {**valid, "metadata": {**metadata, "dimensions": [{"member": "segment"}]}},
        {**valid, "metadata": {**metadata, "concept": "us-gaap:OperatingIncomeLoss"}},
    ]
    filters = {"ticker": "AAPL", "fiscal_year": 2026, "fiscal_period": "Q3"}
    assert evaluate_structured_lookup("What was Apple's net income in Q3 FY2026?", cases, filters) == [valid]


def test_api_preserves_graph_claim_provenance(monkeypatch):
    from fastapi.testclient import TestClient

    import api.main

    metadata = {**ROW["metadata"], "claim_id": "claim", "retrieval_method": "neo4j_fulltext_claim", "trace_id": "claimed"}
    monkeypatch.setattr(api.main, "run_integrated_agent", lambda **_: {
        "status": "SUCCESS", "used_tool": "graph", "evidence": [{"text": "claim", "metadata": metadata}],
        "joint_trace": {},
    })
    data = TestClient(api.main.app).post("/query", json={"query": "Find claims", "trace_id": "claimed"}).json()
    assert data["citations"] == []
    citation = data["retrieval_citations"][0]
    assert (citation["claim_id"], citation["section_id"], citation["retrieval_method"], citation["trace_id"]) == (
        "claim", "s1", "neo4j_fulltext_claim", "claimed",
    )

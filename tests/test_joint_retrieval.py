import sys
from types import ModuleType
from unittest.mock import Mock

import pytest

from agent.joint_retrieval import run_joint_retrieval


@pytest.fixture
def rag_interfaces(monkeypatch):
    coverage = ModuleType("rag.coverage")
    coverage.extract_request = Mock(return_value={
        "companies": ["Apple"], "period_ends": ["2026-03-31"], "fiscal_periods": None,
    })
    coverage.default_index = Mock()
    coverage.check_coverage = Mock()
    retrieve = ModuleType("rag.retrieve")
    retrieve.retrieve_multi = Mock()
    retrieve.retrieve_with_status = retrieve.retrieve_multi
    monkeypatch.setitem(sys.modules, "rag.coverage", coverage)
    monkeypatch.setitem(sys.modules, "rag.retrieve", retrieve)
    return coverage, retrieve.retrieve_multi


def state(question="Compare Microsoft's and Apple's revenue"):
    return {"query": question, "filters": {"ticker": "MSFT", "fiscal_period": "Q1"},
            "question_type": "comparison", "top_k": 15}


@pytest.mark.parametrize("status", ["none", "unresolved", "no_target"])
def test_short_circuits_without_retrieval(rag_interfaces, status):
    coverage, search = rag_interfaces
    coverage.check_coverage.return_value = {
        "status": status, "targets": [], "entities": [], "message": "Coverage message",
    }
    result = run_joint_retrieval(state(), "short", False)
    assert result["answer"] and not result["joint_trace"]["retrieval_called"]
    search.assert_not_called()


def test_periods_from_rules_and_two_tickers_scoped_by_accession(rag_interfaces):
    coverage, search = rag_interfaces
    coverage.check_coverage.return_value = {
        "status": "all_hit", "entities": [], "message": "ok",
        "targets": [
            {"ticker": "MSFT", "status": "hit", "accessions": ["0001193125-26-191507"]},
            {"ticker": "AAPL", "status": "hit", "accessions": ["0000320193-26-000013"]},
        ],
    }
    search.return_value = {"results": [], "subqueries": [{}, {}], "skipped": [],
                           "evidence_status": "empty", "weak_reasons": []}
    result = run_joint_retrieval(state(), "multi", True)
    assert coverage.check_coverage.call_args.kwargs == {
        "companies": ["MSFT", "Apple"], "period_ends": ["2026-03-31"], "fiscal_periods": None,
    }
    request = search.call_args.kwargs
    assert request["trace_id"] == "multi"
    assert request["filters"]["ticker"] == ["MSFT", "AAPL"]
    assert [item["filters"] for item in request["subqueries"]] == [
        {"ticker": "MSFT", "accession_number": ["0001193125-26-191507"]},
        {"ticker": "AAPL", "accession_number": ["0000320193-26-000013"]},
    ]
    assert result["joint_trace"]["n_subqueries"] == 2


@pytest.mark.parametrize("graph_enabled", [False, True])
def test_narrative_accepts_only_provenance_scoped_evidence(rag_interfaces, graph_enabled):
    coverage, search = rag_interfaces
    accession = "0001193125-26-191507"
    coverage.check_coverage.return_value = {
        "status": "partial", "entities": [], "message": "Apple filing unavailable",
        "targets": [{"ticker": "MSFT", "status": "hit", "accessions": [accession]},
                    {"ticker": "AAPL", "status": "miss", "accessions": []}],
    }
    source = {
        "ticker": "MSFT", "form": "10-Q", "accession_number": accession, "chunk_id": "c1",
        "source_url": "https://www.sec.gov/Archives/edgar/data/789019/000119312526191507/test.htm",
        "metadata": {}, "text": "A segment disclosure in MD&A.",
    }
    search.return_value = {"results": [source, {**source, "ticker": "AAPL"}], "subqueries": [{}],
                           "skipped": [], "evidence_status": "ok", "weak_reasons": []}
    request = {**state("Which Microsoft segment includes LinkedIn?"), "question_type": "relationship"}
    result = run_joint_retrieval(request, "narrative", graph_enabled)
    assert result["status"] == "SUCCESS"
    assert result["joint_trace"]["accepted_count"] == 1
    assert result["filters"]["ticker"] == ["MSFT"]


def test_joint_lexical_graph_attempt_precedes_rag(rag_interfaces):
    coverage, vector = rag_interfaces
    coverage.check_coverage.return_value = {
        "status": "all_hit", "entities": [{"ticker": "MSFT"}], "message": "ok",
        "targets": [{"ticker": "MSFT", "status": "hit", "accessions": ["0001193125-26-191507"]}],
    }
    graph = Mock(return_value=[{"text": "A competition disclosure", "metadata": {
        "ticker": "MSFT", "form": "10-Q", "reporting_period_end": "2026-03-31",
        "accession_number": "0001193125-26-191507", "section_id": "s1",
        "source_url": "https://www.sec.gov/Archives/edgar/data/789019/000119312526191507/msft.htm",
    }}])
    result = run_joint_retrieval(state("Find Microsoft claims about competition"), "graph", True, {"graph": graph})
    assert result["used_tool"] == "graph"
    graph.assert_called_once()
    vector.assert_not_called()


def test_joint_quarter_without_year_clarifies(rag_interfaces):
    coverage, vector = rag_interfaces
    coverage.extract_request.return_value = {"companies": [], "fiscal_periods": ["Q3"], "fiscal_years": None}
    coverage.check_coverage.return_value = {"status": "none", "entities": [{"ticker": "MSFT"}],
                                           "targets": [], "message": "none"}
    graph = Mock()
    result = run_joint_retrieval(state("What was Microsoft revenue in Q3?"), "quarter", True, {"graph": graph})
    assert result["selected_tool"] == "clarification"
    assert "fiscal year" in result["answer"]
    vector.assert_not_called()
    graph.assert_not_called()

@pytest.mark.parametrize("ticker,alias", [
    ("AAPL", "Apple"), ("CASY", "Casey's"), ("MCK", "McKesson"), ("MDT", "Medtronic"),
    ("MSFT", "Microsoft"), ("MU", "Micron"), ("NKE", "Nike"), ("NTAP", "NetApp"),
    ("PH", "Parker Hannifin"), ("TTWO", "Take-Two"), ("GOOGL", "Google"),
    ("AMZN", "Amazon"), ("WMT", "Wal-Mart"), ("INTC", "Intel"),
    ("CAH", "Cardinal Health"), ("WDC", "Western Digital"),
])
@pytest.mark.parametrize("status", ["none", "unresolved"])
def test_contract_graph_fallback(rag_interfaces, ticker, alias, status):
    coverage, vector = rag_interfaces
    coverage.check_coverage.return_value = {
        "status": status, "targets": [], "entities": [], "message": "Unavailable in RAG.",
    }
    graph = Mock(return_value=[])
    request = {**state(f"Describe {alias} risks"), "filters": {}, "question_type": None}
    result = run_joint_retrieval(request, "coverage", True, {"graph": graph})
    if ticker in {"CAH", "INTC", "AMZN"}:
        graph.assert_not_called()
        assert not result["joint_trace"]["retrieval_called"]
        assert result["joint_trace"]["graph_coverage_status"] == (
            "no_filing_coverage" if ticker == "AMZN" else "paused")
        return
    graph.assert_called_once()
    assert result["joint_trace"]["graph_route_outcome"] == "no_matching_evidence"
    assert graph.call_args.kwargs["filters"]["ticker"] == ticker
    assert result["joint_trace"]["retrieval_called"]
    assert result["status"] == "NO_EVIDENCE"
    vector.assert_not_called()


def test_bare_cardinal_does_not_resolve_to_cah():
    from agent.query_parser import understand_query

    assert understand_query("Describe Cardinal risks")["ticker"] is None


def test_contract_calculator():
    from agent.calculator import calculate

    fact = {"metric": "revenue", "scope": "consolidated", "unit": "USD millions",
            "duration_months": 3, "period_end": "2026-03-31", "comparative_period_end": "2025-03-31",
            "as_reported": "82,886", "comparative_as_reported": "70,066"}
    row = {"text": "Revenue | 82,886 | 70,066", "metadata": {
        "ticker": "MSFT", "chunk_id": "example", "verified_financial_input": fact,
    }}
    assert "18.3%" in calculate([row], "yoy", ["MSFT"])["answer"]
    assert calculate([{**row, "text": "wrong"}], "yoy", ["MSFT"]) is None
    apple = {**row, "metadata": {**row["metadata"], "ticker": "AAPL",
                                "verified_financial_input": {**fact, "period_end": "2026-06-27"}}}
    answer = calculate([row, apple], "difference", ["MSFT", "AAPL"])["answer"]
    assert "2026-03-31" in answer and "2026-06-27" in answer
    apple["metadata"]["verified_financial_input"]["unit"] = "USD thousands"
    assert calculate([row, apple], "difference", ["MSFT", "AAPL"]) is None


@pytest.mark.parametrize("filing_year,header,accepted", [
    (2023, "", True),
    (2024, "| | Year ended June 30, 2024 | Year ended June 30, 2023 |", True),
    (2024, "", False),
    (2024, "| | Three months ended June 30, 2024 | Three months ended June 30, 2023 |", False),
])
def test_annual_evidence_requires_explicit_comparative_header(filing_year, header, accepted):
    from agent.joint_evidence import scope_annual_evidence

    row = {"metadata": {"form": "10-K", "fiscal_year": filing_year, "is_table": True,
                        "reporting_period_end": f"{filing_year}-06-30"},
           "text": f"(In millions)\n{header}\n| Total Revenue | $100 | $90 |"}
    scoped = scope_annual_evidence(row, "What was revenue in fiscal year 2023?",
                                  {"forms": ["10-K"], "fiscal_years": [2023]})
    assert (scoped is not None) == accepted
    if scoped:
        assert scoped["text"] == row["text"]
        assert scoped["metadata"]["fiscal_year"] == filing_year
        if filing_year == 2024:
            assert scoped["derived_context"]["period_end"] == "2023-06-30"
            assert scoped["derived_context"]["as_reported"] == "$90"
            assert "$100" not in scoped["derived_context"]["answer_text"]


def test_allowed_graph_backend_failure_is_not_coverage(rag_interfaces):
    coverage, _ = rag_interfaces
    coverage.check_coverage.return_value = {
        "status": "unresolved", "targets": [], "entities": [], "message": "Unavailable in RAG.",
    }
    request = {**state("Describe Alphabet risks"), "filters": {}, "question_type": None}
    graph = Mock(side_effect=ConnectionError)
    result = run_joint_retrieval(request, "unavailable", True, {"graph": graph})
    assert result["joint_trace"]["graph_coverage_status"] == "allowlist_only"
    assert result["joint_trace"]["graph_route_outcome"] == "backend_unavailable"

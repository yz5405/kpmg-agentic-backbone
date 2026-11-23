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

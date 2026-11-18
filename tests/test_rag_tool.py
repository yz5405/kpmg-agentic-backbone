"""Adapter tests for agent/tools/rag_tool.py (Member 1 — Real RAG).

Covers RAG Contract v1.1 (retrieve_with_status) and v1.2 (retrieve_multi) handling:
evidence_status / weak_reasons / SEC citation metadata are preserved, top_k 10 and 15 are
passed through unchanged, and mock vs real behaviour is explicit. A fake ``rag.retrieve``
module stands in for the RAG repo, so these tests run without the real index.
"""

import sys
import types

import pytest

from agent.tools import rag_tool
from agent.tools.rag_tool import (
    MOCK_MULTI_WARNING,
    retrieve_evidence_result,
    retrieve_multi_evidence_result,
)

CITATION_KEYS = ("chunk_id", "accession_number", "source_url", "ticker", "form",
                 "reporting_period_end", "section")


def _chunk(ticker="MSFT", rank=1, form="10-Q", **meta):
    return {
        "rank": rank,
        "chunk_id": f"{ticker}-0001-{rank:04d}",
        "text": f"{ticker} total revenue evidence {rank}",
        "score": 0.03,
        "section": "Part I Item 2",
        "ticker": ticker,
        "cik": "0000789019",
        "company_name": f"{ticker} Corp",
        "form": form,
        "accession_number": f"0000000000-26-{rank:06d}",
        "filing_date": "2026-04-29",
        "reporting_period_end": "2026-03-31",
        "source_url": f"https://www.sec.gov/Archives/{ticker}.htm",
        "chunking_version": "C1",
        "extraction_version": "v",
        "index_version": "v",
        "metadata": {"fiscal_year": 2026, "fiscal_period": "Q3", **meta},
    }


@pytest.fixture
def fake_rag(monkeypatch):
    """Install a fake RAG package and switch the adapter to the real backend."""
    calls = []
    module = types.ModuleType("rag.retrieve")

    def retrieve_with_status(query, filters=None, top_k=10, **kw):
        calls.append(("status", filters, top_k))
        return {"results": [_chunk(rank=i) for i in range(1, top_k + 1)],
                "evidence_status": "ok", "weak_reasons": []}

    def retrieve_multi(query, filters=None, top_k=10, trace_id=None, subqueries=None, top_k_each=None):
        calls.append(("multi", filters, top_k, subqueries, top_k_each))
        return {
            "results": [
                _chunk("MSFT", 1, subquery="ticker=MSFT", subquery_rank=1),
                _chunk("AAPL", 2, subquery="ticker=AAPL", subquery_rank=1),
            ],
            "subqueries": [
                {"label": "ticker=MSFT", "n_results": 1, "evidence_status": "ok", "weak_reasons": []},
                {"label": "ticker=AAPL", "n_results": 1, "evidence_status": "weak",
                 "weak_reasons": ["entity_missing"]},
            ],
            "skipped": [],
            "evidence_status": "weak",
            "weak_reasons": ["ticker=AAPL:entity_missing"],
            "warnings": [],
            "trace_id": None,
            "top_k_each": 10,
        }

    module.retrieve = lambda **kw: []
    module.retrieve_with_status = retrieve_with_status
    module.retrieve_multi = retrieve_multi
    monkeypatch.setitem(sys.modules, "rag", types.ModuleType("rag"))
    monkeypatch.setitem(sys.modules, "rag.retrieve", module)
    monkeypatch.setenv("KPMG_RAG_BACKEND", "real")
    return types.SimpleNamespace(module=module, calls=calls)


# ---------------------------------------------------------------- top_k 10 vs 15
@pytest.mark.parametrize("top_k", [10, 15])
def test_top_k_passed_through_unchanged(fake_rag, top_k):
    result = retrieve_evidence_result("Microsoft revenue", {"ticker": "MSFT"}, top_k)
    assert fake_rag.calls == [("status", {"ticker": "MSFT"}, top_k)]
    assert len(result["evidence"]) == top_k
    assert result["evidence_status"] == "ok"


def test_default_top_k_is_still_10(fake_rag):
    retrieve_evidence_result("Microsoft revenue")
    retrieve_multi_evidence_result("Microsoft revenue")
    assert [c[2] for c in fake_rag.calls] == [10, 10]


# ---------------------------------------------------------------- retrieve_multi
def test_multi_preserves_status_reasons_and_subqueries(fake_rag):
    result = retrieve_multi_evidence_result(
        "Compare Microsoft and Apple revenue", {"ticker": ["MSFT", "AAPL"], "form": "10-Q"}, 15
    )
    assert fake_rag.calls[0][:3] == ("multi", {"ticker": ["MSFT", "AAPL"], "form": "10-Q"}, 15)
    assert result["evidence_status"] == "weak"
    assert result["weak_reasons"] == ["ticker=AAPL:entity_missing"]
    assert [s["label"] for s in result["subqueries"]] == ["ticker=MSFT", "ticker=AAPL"]
    assert result["skipped"] == [] and result["warnings"] == []


def test_multi_preserves_sec_citation_and_subquery_metadata(fake_rag):
    result = retrieve_multi_evidence_result("q", {"ticker": ["MSFT", "AAPL"]})
    for item, ticker in zip(result["evidence"], ["MSFT", "AAPL"]):
        meta = item["metadata"]
        assert all(meta.get(k) for k in CITATION_KEYS)
        assert meta["ticker"] == ticker
        assert meta["source"] == "10-Q"  # legacy filing-type meaning kept
        assert meta["subquery"] == f"ticker={ticker}" and meta["subquery_rank"] == 1


def test_multi_passes_subqueries_and_top_k_each(fake_rag):
    sq = [{"query": "MSFT revenue", "filters": {"ticker": "MSFT"}, "label": "MSFT"}]
    retrieve_multi_evidence_result("q", None, 10, subqueries=sq, top_k_each=5)
    assert fake_rag.calls[0][3:] == (sq, 5)


def test_multi_has_same_keys_as_single_result(fake_rag):
    single = retrieve_evidence_result("q")
    multi = retrieve_multi_evidence_result("q")
    assert set(single) <= set(multi)


# ---------------------------------------------------------------- weak / empty / errors
def test_empty_status_preserved(fake_rag):
    fake_rag.module.retrieve_multi = lambda **kw: {
        "results": [], "subqueries": [], "skipped": [], "warnings": ["no filing for MSFT FY2025"],
        "evidence_status": "empty", "weak_reasons": ["ticker=MSFT:filter_no_match"]}
    result = retrieve_multi_evidence_result("q", {"ticker": "MSFT", "fiscal_year": 2025})
    assert result["evidence"] == []
    assert result["evidence_status"] == "empty"
    assert result["weak_reasons"] == ["ticker=MSFT:filter_no_match"]
    assert result["warnings"] == ["no filing for MSFT FY2025"]


@pytest.mark.parametrize("bad", [0, -1, 51, True, 2.5])
def test_multi_invalid_top_k_raises_before_calling_rag(fake_rag, bad):
    with pytest.raises(ValueError):
        retrieve_multi_evidence_result("q", top_k=bad)
    assert fake_rag.calls == []


def test_multi_upstream_error_propagates(fake_rag):
    def broken(**kw):
        raise RuntimeError("chroma index missing")
    fake_rag.module.retrieve_multi = broken
    with pytest.raises(RuntimeError, match="chroma index missing"):
        retrieve_multi_evidence_result("q")


def test_multi_requires_rag_v12(fake_rag):
    del fake_rag.module.retrieve_multi
    with pytest.raises(ImportError, match="v1.2"):
        retrieve_multi_evidence_result("q")


# ---------------------------------------------------------------- mock backend
def test_mock_multi_runs_single_search_and_says_so(monkeypatch):
    monkeypatch.setenv("KPMG_RAG_BACKEND", "mock")
    result = retrieve_multi_evidence_result(
        "What was Microsoft's total revenue?", {"ticker": "MSFT", "fiscal_year": 2026, "fiscal_period": "Q3"}
    )
    assert result["evidence"]
    assert result["subqueries"] == []
    assert result["warnings"] == [MOCK_MULTI_WARNING]


def test_multi_works_as_workflow_retriever(fake_rag):
    from agent.graph_workflow import run_graph_agent

    result = run_graph_agent(
        query="Compare Microsoft and Apple revenue",
        parser=lambda q: {"ticker": ["MSFT", "AAPL"], "form": "10-Q"},
        retriever=retrieve_multi_evidence_result,
    )
    assert result["evidence_status"] == "weak"
    assert result["weak_reasons"] == ["ticker=AAPL:entity_missing"]
    assert len(result["evidence"]) == 2

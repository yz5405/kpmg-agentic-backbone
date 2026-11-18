"""Tests for the unified SEC citation schema (agent/citations.py).

Run:
    python -m pytest tests/test_citations.py -v
"""

import pytest

from agent.citations import (
    build_citation,
    build_citations,
    validate_citation,
    validate_provenance,
)
from agent.tools.rag_tool import retrieve_evidence


QUOTE = "Total revenue 82,886 70,066"


def sample_evidence():
    """Adapter-normalized evidence item matching docs/function_contractsv2.md §5."""
    return {
        "text": QUOTE,
        "metadata": {
            "ticker": "MSFT",
            "cik": "0000789019",
            "company_name": "Microsoft Corporation",
            "form": "10-Q",
            "accession_number": "0001193125-26-191507",
            "filing_date": "2026-04-29",
            "reporting_period_end": "2026-03-31",
            "fiscal_year": 2026,
            "fiscal_period": "Q3",
            "chunk_id": "MSFT-0001193125-26-191507-0001",
            "section": "Part I Item 1",
            "section_title": "Income Statements",
            "is_table": True,
            "source_url": (
                "https://www.sec.gov/Archives/edgar/data/"
                "789019/000119312526191507/msft-20260331.htm"
            ),
            "retrieval_method": "mock_keyword_overlap",
        },
    }


def test_build_citation_normalized_shape():
    citation = build_citation(sample_evidence())

    assert citation["quote"] == QUOTE
    assert citation["ticker"] == "MSFT"
    assert citation["cik"] == "0000789019"
    assert citation["form_type"] == "10-Q"               # from the "form" alias
    assert citation["accession_number"] == "0001193125-26-191507"
    assert citation["fiscal_year"] == 2026
    assert citation["fiscal_period"] == "Q3"
    assert citation["section_title"] == "Income Statements"
    assert citation["is_table"] is True


def test_build_citation_accepts_flat_chunk():
    # Raw RetrievedChunk: fields flat, "metadata" nested.
    flat = {
        "chunk_id": "MSFT-0001193125-26-191507-0001",
        "text": QUOTE,
        "section": "Part I Item 1",
        "ticker": "MSFT",
        "cik": "0000789019",
        "form": "10-Q",
        "accession_number": "0001193125-26-191507",
        "metadata": {"section_title": "Income Statements", "is_table": False},
    }
    citation = build_citation(flat)

    assert citation["quote"] == QUOTE
    assert citation["form_type"] == "10-Q"
    assert citation["section_title"] == "Income Statements"
    assert citation["is_table"] is False


def test_field_aliases():
    item = {
        "text": QUOTE,
        "metadata": {
            "form_type": "10-K",
            "accession": "0001193125-26-191507",
            "company": "Microsoft Corporation",
        },
    }
    citation = build_citation(item)

    assert citation["form_type"] == "10-K"
    assert citation["accession_number"] == "0001193125-26-191507"
    assert citation["company_name"] == "Microsoft Corporation"


def test_normalization():
    item = {
        "text": QUOTE,
        "metadata": {
            "ticker": "msft",
            "accession_number": "000119312526191507",  # 18 digits, no dashes
            "fiscal_period": "q3",
            "fiscal_year": "2026",
        },
    }
    citation = build_citation(item)

    assert citation["ticker"] == "MSFT"
    assert citation["accession_number"] == "0001193125-26-191507"
    assert citation["fiscal_period"] == "Q3"
    assert citation["fiscal_year"] == 2026


def test_missing_text_raises():
    with pytest.raises(ValueError):
        build_citation({"metadata": {"ticker": "MSFT"}})


def test_non_dict_raises():
    with pytest.raises(ValueError):
        build_citation("not a dict")  # type: ignore[arg-type]


def test_build_citations_from_mock_retriever():
    evidence = retrieve_evidence(
        "What was Microsoft's total revenue for the three months ended March 31, 2026?",
        filters={"ticker": "MSFT", "form": "10-Q"},
        top_k=3,
    )
    citations = build_citations(evidence)

    assert len(citations) == len(evidence)
    assert all(validate_citation(c) == [] for c in citations)
    assert all(c["ticker"] == "MSFT" for c in citations)
    assert all(c["form_type"] == "10-Q" for c in citations)


def test_validate_valid_citation_no_problems():
    citation = build_citation(sample_evidence())
    assert validate_citation(citation) == []


def test_validate_minimal_citation_is_valid():
    # Optional fields may all be absent; only quote is required.
    assert validate_citation(build_citation({"text": "some evidence text"})) == []


def test_validate_bad_accession():
    citation = build_citation({"text": QUOTE, "metadata": {"accession_number": "not-an-accession"}})
    problems = validate_citation(citation)
    assert any("accession_number" in p for p in problems)


def test_validate_bad_date():
    citation = build_citation({"text": QUOTE, "metadata": {"filing_date": "2026-13-40"}})
    problems = validate_citation(citation)
    assert any("filing_date" in p for p in problems)


def test_validate_bad_url():
    citation = build_citation({"text": QUOTE, "metadata": {"source_url": "https://example.com/x"}})
    problems = validate_citation(citation)
    assert any("source_url" in p for p in problems)


def test_validate_bad_fiscal_period():
    citation = build_citation({"text": QUOTE, "metadata": {"fiscal_period": "Q5"}})
    problems = validate_citation(citation)
    assert any("fiscal_period" in p for p in problems)


def test_validate_bad_cik():
    citation = build_citation({"text": QUOTE, "metadata": {"cik": "abc"}})
    problems = validate_citation(citation)
    assert any("cik" in p for p in problems)


def test_validate_provenance_summary():
    good = build_citation(sample_evidence())
    bad = build_citation({"text": QUOTE, "metadata": {"cik": "abc"}})
    summary = validate_provenance([good, bad])

    assert summary["total"] == 2
    assert summary["valid"] == 1
    assert summary["invalid"] == 1
    assert summary["errors"][0]["index"] == 1

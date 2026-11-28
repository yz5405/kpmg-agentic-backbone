"""Adapt GraphRAG retrieval to Agent evidence."""

import re
from itertools import product

from agent.tools.rag_tool import _to_evidence


def retrieve_structured_evidence(
    query: str,
    filters: dict | None = None,
    top_k: int = 10,
    trace_id: str | None = None,
) -> list[dict]:
    """Call the registered GraphRAG structured backend when fallback runs."""
    from graphrag.backends import structured_search

    return _retrieve_evidence(structured_search, query, filters, top_k, trace_id)


def retrieve_graph_evidence(
    query: str,
    filters: dict | None = None,
    top_k: int = 10,
    trace_id: str | None = None,
) -> list[dict]:
    """Call the registered Neo4j full-text retrieval arm."""
    from graphrag.backends import graph_search

    return _retrieve_evidence(graph_search, query, filters, top_k, trace_id)


def _retrieve_evidence(search, query: str, filters: dict | None, top_k: int, trace_id: str | None) -> list[dict]:
    from graphrag.contract import FilterNotSupportedError

    retrieval_filters = {key: value for key, value in (filters or {}).items() if value is not None}
    if retrieval_filters.keys() - {"ticker", "form", "fiscal_year", "fiscal_period", "reporting_period_end", "section"}:
        raise FilterNotSupportedError("Agent GraphRAG does not support this filter")
    if "section" in retrieval_filters:
        retrieval_filters["section"] = re.sub(r"[\s_-]+", "-", retrieval_filters["section"].strip().lower())
    # Only ticker is documented as list-valued. Preserve all other requested
    # scopes using scalar searches and the same caller trace ID.
    split_keys = [key for key, value in retrieval_filters.items() if key != "ticker" and isinstance(value, list)]
    rows = []
    for values in product(*(retrieval_filters[key] for key in split_keys)):
        scope = {**retrieval_filters, **dict(zip(split_keys, values))}
        if scope.get("reporting_period_end") and not scope.get("fiscal_year"):
            scope.pop("fiscal_period", None)
        rows.extend(search(query=query, filters=scope, top_k=top_k, trace_id=trace_id))
    evidence = [_to_evidence(row) for row in rows]
    for item in evidence:
        metadata = item["metadata"]
        if not metadata.get("source_url"):
            citation = _sec_filing_index(metadata)
            if citation is not None:
                metadata["source_url"] = citation
    return evidence


def _sec_filing_index(metadata: dict) -> str | None:
    cik = metadata.get("cik")
    accession = metadata.get("accession_number")
    if not isinstance(cik, str) or not re.fullmatch(r"[0-9]{1,10}", cik) or int(cik) == 0:
        return None
    if not isinstance(accession, str) or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
        return None
    directory = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{directory}/{accession}-index.htm"

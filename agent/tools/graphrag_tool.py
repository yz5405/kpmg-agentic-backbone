"""Adapt GraphRAG structured retrieval to Agent evidence."""

import re

from agent.tools.rag_tool import _to_evidence


def retrieve_structured_evidence(
    query: str,
    filters: dict | None = None,
    top_k: int = 8,
) -> list[dict]:
    """Call the registered GraphRAG structured backend when fallback runs."""
    from graphrag.retrieve import structured_search

    structured_filters = {
        key: value
        for key, value in (filters or {}).items()
        if key in {"ticker", "fiscal_year", "fiscal_period"} and value is not None
    }
    rows = structured_search(query=query, filters=structured_filters, top_k=top_k)
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

"""Unified SEC citation schema and provenance validation (Task 4 — SEC Citations).

Turns the heterogeneous evidence items produced by the RAG adapter
(``agent/tools/rag_tool.retrieve_evidence``) into one normalized citation
shape, and validates that each citation is internally consistent enough to be
rendered next to a generated answer.

Scope (agreed with team):
- RAG only. The builder accepts both the raw ``RetrievedChunk`` shape (flat
  fields + optional nested ``metadata``) and the adapter's normalized
  ``{"text", "metadata"}`` shape, and maps several known field-name aliases so
  the real RAG Team contract can land later without rewriting this module.
  GraphRAG fields can be added by extending ``_FIELD_ALIASES`` without touching
  the public API.
- Offline schema + format validation. The EDGAR URL is checked for shape only;
  nothing is resolved over the network.

This module is standalone and deliberately does NOT modify shared graph state.
Wiring a ``citations`` field into ``AgentGraphState`` is a Team-Lead-approved
contract change and is left out of scope here.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, TypedDict


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class Citation(TypedDict):
    """Normalized SEC filing citation.

    Every key is always present; fields that could not be recovered from the
    source evidence are ``None`` so downstream consumers can rely on the shape.
    """

    quote: str                          # verbatim evidence text being cited
    ticker: str | None
    cik: str | None                     # up to 10 digits, zero-padded
    company_name: str | None
    form_type: str | None               # "10-Q", "10-K", "8-K", ...
    accession_number: str | None        # "0001193125-26-191507"
    filing_date: str | None             # YYYY-MM-DD
    reporting_period_end: str | None    # YYYY-MM-DD
    fiscal_year: int | None
    fiscal_period: str | None           # FY / Q1..Q4
    chunk_id: str | None
    section: str | None                 # "Part I Item 1"
    section_title: str | None           # "Income Statements"
    is_table: bool | None
    source_url: str | None              # sec.gov Archives URL
    retrieval_method: str | None        # "mock_keyword_overlap", ...


# Canonical field -> accepted source keys, first match wins.
#
# "source" maps to form_type (not source_url) to match the codebase convention
# in ``agent/tools/rag_tool._to_evidence``, which sets ``metadata["source"]``
# to the filing form type.
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "ticker": ("ticker",),
    "cik": ("cik", "cik_number"),
    "company_name": ("company_name", "company", "registrant"),
    "form_type": ("form_type", "form", "filing_type", "source"),
    "accession_number": ("accession_number", "accession", "accession_no"),
    "filing_date": ("filing_date", "filed", "date_filed"),
    "reporting_period_end": (
        "reporting_period_end", "period_of_report", "report_period", "period_end",
    ),
    "fiscal_year": ("fiscal_year", "fy"),
    "fiscal_period": ("fiscal_period", "period", "quarter"),
    "chunk_id": ("chunk_id", "chunkId", "id"),
    "section": ("section",),
    "section_title": ("section_title", "title"),
    "is_table": ("is_table",),
    "source_url": ("source_url", "sec_url", "url"),
    "retrieval_method": ("retrieval_method",),
}


# ---------------------------------------------------------------------------
# Normalizers (light coercion so one "unified" shape comes out)
# ---------------------------------------------------------------------------

def _clean_str(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


def _upper(value: Any) -> str | None:
    text = _clean_str(value)
    return text.upper() if text else None


def _cik(value: Any) -> str | None:
    text = _clean_str(value)
    if text is None:
        return None
    return text.zfill(10) if text.isdigit() else text


def _accession(value: Any) -> str | None:
    text = _clean_str(value)
    if text is None:
        return None
    # Normalize a bare 18-digit accession into the dashed EDGAR form.
    if text.isdigit() and len(text) == 18:
        return f"{text[:10]}-{text[10:12]}-{text[12:]}"
    return text


def _year(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_NORMALIZERS: dict[str, Any] = {
    "ticker": _upper,
    "cik": _cik,
    "company_name": _clean_str,
    "form_type": _upper,
    "accession_number": _accession,
    "filing_date": _clean_str,
    "reporting_period_end": _clean_str,
    "fiscal_year": _year,
    "fiscal_period": _upper,
    "chunk_id": _clean_str,
    "section": _clean_str,
    "section_title": _clean_str,
    "is_table": lambda v: v if isinstance(v, bool) else None,
    "source_url": _clean_str,
    "retrieval_method": _clean_str,
}


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def _first(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def build_citation(evidence_item: dict[str, Any]) -> Citation:
    """Normalize one evidence item into a :class:`Citation`.

    Accepts both shapes emitted in this project:
    - raw ``RetrievedChunk`` (flat fields + optional nested ``metadata``)
    - adapter evidence ``{"text", "metadata": {...}}``
    """
    if not isinstance(evidence_item, dict):
        raise ValueError("evidence item must be a dict")
    if "text" not in evidence_item or not isinstance(evidence_item["text"], str):
        raise ValueError("evidence item must have a string 'text' field")

    metadata = evidence_item.get("metadata")
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError("'metadata' must be a dict when present")

    # Flatten: top-level fields first, nested metadata overrides on conflict.
    raw: dict[str, Any] = {**evidence_item, **metadata}

    return {
        "quote": evidence_item["text"],
        "ticker": _NORMALIZERS["ticker"](_first(raw, _FIELD_ALIASES["ticker"])),
        "cik": _NORMALIZERS["cik"](_first(raw, _FIELD_ALIASES["cik"])),
        "company_name": _NORMALIZERS["company_name"](_first(raw, _FIELD_ALIASES["company_name"])),
        "form_type": _NORMALIZERS["form_type"](_first(raw, _FIELD_ALIASES["form_type"])),
        "accession_number": _NORMALIZERS["accession_number"](_first(raw, _FIELD_ALIASES["accession_number"])),
        "filing_date": _NORMALIZERS["filing_date"](_first(raw, _FIELD_ALIASES["filing_date"])),
        "reporting_period_end": _NORMALIZERS["reporting_period_end"](_first(raw, _FIELD_ALIASES["reporting_period_end"])),
        "fiscal_year": _NORMALIZERS["fiscal_year"](_first(raw, _FIELD_ALIASES["fiscal_year"])),
        "fiscal_period": _NORMALIZERS["fiscal_period"](_first(raw, _FIELD_ALIASES["fiscal_period"])),
        "chunk_id": _NORMALIZERS["chunk_id"](_first(raw, _FIELD_ALIASES["chunk_id"])),
        "section": _NORMALIZERS["section"](_first(raw, _FIELD_ALIASES["section"])),
        "section_title": _NORMALIZERS["section_title"](_first(raw, _FIELD_ALIASES["section_title"])),
        "is_table": _NORMALIZERS["is_table"](_first(raw, _FIELD_ALIASES["is_table"])),
        "source_url": _NORMALIZERS["source_url"](_first(raw, _FIELD_ALIASES["source_url"])),
        "retrieval_method": _NORMALIZERS["retrieval_method"](_first(raw, _FIELD_ALIASES["retrieval_method"])),
    }


def build_citations(evidence: list[dict[str, Any]]) -> list[Citation]:
    """Normalize a full evidence list into citations."""
    if not isinstance(evidence, list):
        raise ValueError("evidence must be a list")
    return [build_citation(item) for item in evidence]


# ---------------------------------------------------------------------------
# Provenance validation (offline, format-level)
# ---------------------------------------------------------------------------

_ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CIK_RE = re.compile(r"^\d{1,10}$")
_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")
_FORM_RE = re.compile(r"^[A-Z0-9]{1,4}(?:-[A-Z0-9]{1,4})?(?:/[A-Z]{1,3})?$")
_VALID_PERIODS = {"FY", "Q1", "Q2", "Q3", "Q4"}


def _is_real_date(text: str) -> bool:
    try:
        date.fromisoformat(text)
        return True
    except ValueError:
        return False


def validate_citation(citation: Citation) -> list[str]:
    """Return a list of provenance problems for one citation (empty == valid).

    Validation is offline and structural: it checks field formats and internal
    consistency, but does not resolve the source URL over the network.
    """
    problems: list[str] = []

    def check(field: str, value: Any, ok: bool, detail: str) -> None:
        if not ok:
            problems.append(f"{field}: {detail} (got {value!r})")

    # quote is the only required field.
    check(
        "quote", citation["quote"],
        bool(citation["quote"] and citation["quote"].strip()),
        "must be non-empty",
    )

    ticker = citation["ticker"]
    if ticker is not None:
        check("ticker", ticker, bool(_TICKER_RE.match(ticker)), "unexpected ticker format")

    cik = citation["cik"]
    if cik is not None:
        check("cik", cik, bool(_CIK_RE.match(cik)), "must be 1-10 digits")

    form = citation["form_type"]
    if form is not None:
        check("form_type", form, bool(_FORM_RE.match(form)), "unexpected form type")

    acc = citation["accession_number"]
    if acc is not None:
        check("accession_number", acc, bool(_ACCESSION_RE.match(acc)), "must be like 0001193125-26-191507")

    for name in ("filing_date", "reporting_period_end"):
        value = citation[name]
        if value is not None:
            check(
                name, value,
                bool(_DATE_RE.match(value) and _is_real_date(value)),
                "must be a real YYYY-MM-DD date",
            )

    year = citation["fiscal_year"]
    if year is not None:
        check("fiscal_year", year, 1990 <= year <= 2100, "must be an integer year in 1990-2100")

    period = citation["fiscal_period"]
    if period is not None:
        check("fiscal_period", period, period in _VALID_PERIODS, "must be FY/Q1/Q2/Q3/Q4")

    url = citation["source_url"]
    if url is not None:
        ok_url = (
            url.startswith("https://")
            and "sec.gov" in url
            and "/Archives/edgar/data/" in url
        )
        check("source_url", url, ok_url, "must be a sec.gov EDGAR Archives URL")

    chunk_id = citation["chunk_id"]
    if chunk_id is not None:
        check("chunk_id", chunk_id, bool(chunk_id), "must be a non-empty string")

    is_table = citation["is_table"]
    if is_table is not None:
        check("is_table", is_table, isinstance(is_table, bool), "must be true/false")

    method = citation["retrieval_method"]
    if method is not None:
        check("retrieval_method", method, bool(method), "must be a non-empty string")

    return problems


def validate_provenance(citations: list[Citation]) -> dict[str, Any]:
    """Validate a list of citations and return a summary."""
    if not isinstance(citations, list):
        raise ValueError("citations must be a list")

    errors: list[dict[str, Any]] = []
    for index, citation in enumerate(citations):
        problems = validate_citation(citation)
        if problems:
            errors.append({"index": index, "citation": citation, "problems": problems})

    return {
        "total": len(citations),
        "valid": len(citations) - len(errors),
        "invalid": len(errors),
        "errors": errors,
    }


if __name__ == "__main__":
    from agent.tools.rag_tool import retrieve_evidence

    evidence = retrieve_evidence(
        "What was Microsoft's total revenue for the three months ended March 31, 2026?",
        filters={"ticker": "MSFT"},
        top_k=3,
    )
    citations = build_citations(evidence)
    for citation in citations:
        print(
            f"{citation['form_type']} | {citation['accession_number']} | "
            f"{citation['section_title']} | {citation['source_url']}"
        )
    print(validate_provenance(citations))

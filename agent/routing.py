"""Conditional routing for agent workflow results."""
import re
from datetime import datetime
from math import isfinite
from typing import Protocol
from urllib.parse import urlsplit

from agent.query_parser import COMPANY_TICKERS, KNOWN_TICKERS, understand_query

from agent.state import AgentState, SUCCESS, NO_EVIDENCE, ERROR


class EvidenceEvaluator(Protocol):
    """Select the evidence sufficient to answer the original query."""

    def __call__(
        self,
        *,
        query: str,
        rag_evidence: list[dict],
        graphrag_evidence: list[dict],
        evidence_status: str | None,
        weak_reasons: list[str],
    ) -> list[dict]:
        """Return accepted evidence, or an empty list to abstain."""
        ...


_COMPANY_NAMES = "|".join(re.escape(name) for name in sorted(COMPANY_TICKERS.keys() | KNOWN_TICKERS))
_METRIC_LABELS = {
    "revenue": r"(?:total\s+)?revenue",
    "operating income": r"operating\s+income",
    "net income": r"net\s+income",
}
_SIMPLE_FINANCIAL_QUERY = re.compile(
    rf"(?:what\s+(?:was|is)\s+)?(?:the\s+)?(?:{_COMPANY_NAMES})(?:['’]s)?\s+"
    r"(?:total\s+)?(?P<metric>revenue|operating\s+income|net\s+income)\s+"
    r"(?:in|for)\s+(?:the\s+)?"
    r"(?:Q[1-4]\s+(?:FY|fiscal\s+year)\s*\d{4}|"
    r"(?:FY|fiscal\s+year)\s*\d{4}\s+Q[1-4]|"
    r"three\s+months\s+ended\s+March\s+31,?\s+2026)\s*\??",
    re.IGNORECASE,
)
_AMOUNT = r"-?\s*\$?\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:\s+(?:thousand|million|billion|trillion))?"

_INCOME_STATEMENT_HEADER = re.compile(
    r"INCOME STATEMENTS\s+\(In millions, except per share amounts\)\s+"
    r"(?:\(Unaudited\)\s+)?Three Months Ended\s+(?P<month_day>[A-Za-z]+\s+\d{1,2}),\s+"
    r"Nine Months Ended\s+(?P=month_day),\s+"
    r"(?P<year>\d{4})\s+(?P<prior_year>\d{4})\s+(?P=year)\s+(?P=prior_year)\b",
    re.IGNORECASE,
)
_INCOME_STATEMENT_ROWS = {
    "revenue": "Total revenue",
    "operating income": "Operating income",
    "net income": "Net income",
}


_MSFT_ANNUAL_REVENUE_QUERY = re.compile(
    r"(?:what\s+(?:was|is)\s+)?(?:the\s+)?(?:Microsoft|MSFT)(?:['’]s)?\s+"
    r"(?:total\s+)?revenue\s+(?:in|for)\s+(?:the\s+)?"
    r"(?:FY|fiscal\s+year)\s*(?P<year>\d{4})\s*\??",
    re.IGNORECASE,
)
_REVENUE_CONCEPT = "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"


def evaluate_financial_evidence(
    *,
    query: str,
    rag_evidence: list[dict],
    graphrag_evidence: list[dict],
    evidence_status: str | None,
    weak_reasons: list[str],
) -> list[dict]:
    """Select cited evidence for a supported financial metric query.

    Retrieval signals can trigger fallback upstream. Both evidence sources
    must satisfy the same checks here.
    """
    annual = _MSFT_ANNUAL_REVENUE_QUERY.fullmatch(query.strip())
    if annual is not None:
        return _select_msft_annual_revenue(graphrag_evidence, int(annual["year"]))

    match = _SIMPLE_FINANCIAL_QUERY.fullmatch(query.strip())
    if match is None:
        return []

    filters = understand_query(query)
    if None in filters.values():
        return []

    metric = " ".join(match["metric"].lower().split())
    label = _METRIC_LABELS[metric]
    amount_line = re.compile(rf"{label}\s*(?:[:=]|\bwas\b)?\s+{_AMOUNT}\s*\.?", re.IGNORECASE)

    return [
        item
        for item in (*rag_evidence, *graphrag_evidence)
        if _supports_financial_metric(item, filters, metric, amount_line)
    ]


def _supports_financial_metric(
    item: dict, filters: dict, metric: str, amount_line: re.Pattern
) -> bool:
    metadata = item.get("metadata")
    if not isinstance(metadata, dict) or any(metadata.get(key) != value for key, value in filters.items()):
        return False

    if not _has_citation(metadata):
        return False

    text = item.get("text")
    if not isinstance(text, str):
        return False
    if any(amount_line.fullmatch(line.strip()) for line in text.splitlines()):
        return True
    return _supports_income_statement(text, metadata, metric)


def _select_msft_annual_revenue(evidence: list[dict], year: int) -> list[dict]:
    """Accept cited Microsoft 10-K revenue for the July-to-June fiscal year."""
    accepted = []
    for item in evidence:
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            continue
        if (
            metadata.get("ticker") != "MSFT"
            or metadata.get("form") != "10-K"
            or metadata.get("concept") != _REVENUE_CONCEPT
            or metadata.get("period_start") != f"{year - 1:04d}-07-01"
            or metadata.get("period_end") != f"{year:04d}-06-30"
            or metadata.get("dimensions") != []
            or not metadata.get("fact_id")
            or not _has_citation(metadata)
        ):
            continue
        # The backend may preserve the raw XBRL unit ID in unit_ref.
        # Its generated text ends with the resolved currency.
        unit_ref = metadata.get("unit_ref")
        text = item.get("text")
        if unit_ref not in ("USD", "iso4217:USD") and not (
            isinstance(text, str) and text.endswith(" USD")
        ):
            continue
        value = metadata.get("value_num")
        if type(value) in (int, float) and isfinite(value):
            accepted.append(item)

    if len({item["metadata"]["value_num"] for item in accepted}) > 1:
        return []
    return accepted


def _has_citation(metadata: dict) -> bool:
    source_url = metadata.get("source_url")
    if not isinstance(source_url, str):
        return False
    try:
        citation = urlsplit(source_url.strip())
        return citation.scheme in {"http", "https"} and bool(citation.hostname)
    except ValueError:
        return False


def _supports_income_statement(text: str, metadata: dict, metric: str) -> bool:
    """Recognize the four-column Q3 income statement layout used by the demo."""
    if metadata.get("is_table") is not True or metadata.get("fiscal_period") != "Q3":
        return False

    header = _INCOME_STATEMENT_HEADER.match(text.strip())
    if header is None or int(header["year"]) != int(header["prior_year"]) + 1:
        return False

    try:
        quarter_end = datetime.strptime(
            f"{header['month_day']} {header['year']}", "%B %d %Y"
        ).date()
    except ValueError:
        return False
    if quarter_end.isoformat() != metadata.get("reporting_period_end"):
        return False

    # The verified header puts the current quarter in the first of four columns.
    label = _INCOME_STATEMENT_ROWS[metric]
    row = rf"(?<!\w){label}(?:\s+{_AMOUNT}){{4}}(?=\s+[A-Za-z]|\s*$)"
    return re.search(row, header.string[header.end():], re.IGNORECASE) is not None


def determine_status(
    evidence: list[dict],
    error: str | None
) -> str:
    """Determine routing status based on evidence and error."""
    if error is not None:
        return ERROR

    if evidence:
        return SUCCESS

    return NO_EVIDENCE


def should_try_graphrag(evidence_status: str | None, workflow_status: str) -> bool:
    """Decide whether the RAG signal warrants a GraphRAG attempt."""
    return workflow_status != ERROR and evidence_status in {"weak", "empty"}


def route_result(state: AgentState) -> AgentState:
    """Update and return the legacy workflow state."""
    state.status = determine_status(
        evidence=state.evidence,
        error=state.error
    )
    return state

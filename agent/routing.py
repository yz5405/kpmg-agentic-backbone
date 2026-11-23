"""Conditional routing for agent workflow results."""
import re
from datetime import date, datetime
from itertools import takewhile
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
_MARKDOWN_INCOME_STATEMENT_HEADER = re.compile(
    r"(?:ITEM 1\. FINANCIAL STATEMENTS\s*\n)?INCOME STATEMENTS\s*\n"
    r"\(In millions, except per share amounts\)(?:[ \t]+\(Unaudited\))?\s*\n"
    r"\|[ \t]*\| Three Months Ended (?P<month_day>[A-Za-z]+ \d{1,2}), (?P<year>\d{4}) "
    r"\| Three Months Ended (?P=month_day), (?P<prior_year>\d{4}) "
    r"\| Nine Months Ended (?P=month_day), (?P=year) "
    r"\| Nine Months Ended (?P=month_day), (?P=prior_year) \|",
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


_STRUCTURED_CONCEPTS = {
    "revenue": {_REVENUE_CONCEPT, "us-gaap:Revenues", "us-gaap:SalesRevenueNet"},
    "net income": {"us-gaap:NetIncomeLoss"},
    "operating income": {"us-gaap:OperatingIncomeLoss"},
}


def evaluate_structured_lookup(query, evidence, filters):
    """Accept only a single comparable consolidated USD fact for a scoped lookup."""
    annual = _MSFT_ANNUAL_REVENUE_QUERY.fullmatch(query.strip())
    if annual:
        year = int(annual["year"])
        return _select_msft_revenue(
            evidence, form="10-K", start=f"{year-1:04d}-07-01", end=f"{year:04d}-06-30",
        )
    match = _SIMPLE_FINANCIAL_QUERY.fullmatch(query.strip())
    ticker = filters.get("ticker")
    requested_end = filters.get("reporting_period_end")
    period = filters.get("fiscal_period")
    if not match or not isinstance(ticker, str) or (not requested_end and (
        not isinstance(filters.get("fiscal_year"), int) or period not in {"Q1", "Q2", "Q3"}
    )):
        return []
    metric = " ".join(match["metric"].lower().split())
    accepted = []
    for item in evidence:
        metadata = item["metadata"]
        value = metadata.get("value_num")
        if (
            metadata.get("ticker") != ticker or metadata.get("form") != "10-Q"
            or metadata.get("concept") not in _STRUCTURED_CONCEPTS[metric]
            or metadata.get("dimensions") != [] or not metadata.get("fact_id")
            or type(value) not in (int, float) or not isfinite(value)
            or not item["text"].endswith(" USD")
        ):
            continue
        try:
            start = date.fromisoformat(metadata["period_start"])
            end = date.fromisoformat(metadata["period_end"])
        except (KeyError, ValueError, TypeError):
            continue
        if not 75 <= (end - start).days <= 105 or (requested_end and end.isoformat() != requested_end):
            continue
        accepted.append(item)
    facts = {(r["metadata"]["period_start"], r["metadata"]["period_end"], r["metadata"]["value_num"]) for r in accepted}
    return accepted if len(facts) == 1 else []


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
        year = int(annual["year"])
        return _select_msft_revenue(
            graphrag_evidence, form="10-K", start=f"{year - 1:04d}-07-01", end=f"{year:04d}-06-30",
        )

    match = _SIMPLE_FINANCIAL_QUERY.fullmatch(query.strip())
    if match is None:
        return []

    filters = understand_query(query)
    if None in filters.values():
        return []

    metric = " ".join(match["metric"].lower().split())
    label = _METRIC_LABELS[metric]
    amount_line = re.compile(rf"{label}\s*(?:[:=]|\bwas\b)?\s+{_AMOUNT}\s*\.?", re.IGNORECASE)

    accepted = [
        item
        for item in (*rag_evidence, *graphrag_evidence)
        if _supports_financial_metric(item, filters, metric, amount_line)
    ]
    if accepted or metric != "revenue" or filters["ticker"] != "MSFT" or filters["fiscal_period"] != "Q3":
        return accepted

    year = filters["fiscal_year"]
    return _select_msft_revenue(
        graphrag_evidence, form="10-Q", start=f"{year:04d}-01-01", end=f"{year:04d}-03-31",
    )


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


def _select_msft_revenue(evidence: list[dict], *, form: str, start: str, end: str) -> list[dict]:
    """Accept a cited consolidated Microsoft revenue fact for an exact reporting interval."""
    accepted = []
    for item in evidence:
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            continue
        if (
            metadata.get("ticker") != "MSFT"
            or metadata.get("form") != form
            or metadata.get("concept") != _REVENUE_CONCEPT
            or metadata.get("period_start") != start
            or metadata.get("period_end") != end
            or metadata.get("dimensions") != []
            or not metadata.get("fact_id")
            or not _has_citation(metadata)
        ):
            continue
        # unit_ref is a raw XBRL ID. The backend renders the resolved unit in text.
        text = item.get("text")
        if not isinstance(text, str) or not text.endswith(" USD"):
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

    markdown_header = _MARKDOWN_INCOME_STATEMENT_HEADER.match(text.strip())
    header = markdown_header or _INCOME_STATEMENT_HEADER.match(text.strip())
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
    if markdown_header is not None:
        cells = rf"(?:[ \t]*{_AMOUNT}[ \t]*\|){{4}}"
        row = re.compile(rf"\|[ \t]*{label}[ \t]*\|{cells}", re.IGNORECASE)
        lines = header.string[header.end():].lstrip("\n").splitlines()
        table_rows = takewhile(lambda line: line.strip().startswith("|"), lines)
        return any(row.fullmatch(line.strip()) for line in table_rows)

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

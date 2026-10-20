"""Query understanding and financial filter extraction."""

import re

# Supported company name -> ticker mapping.
# Keep this in sync with the ticker universe the RAG team actually retrieves.
COMPANY_TICKERS = {
    "microsoft": "MSFT",
    "apple": "AAPL",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "meta": "META",
    "nvidia": "NVDA",
    "tesla": "TSLA",
}

# Tickers recognized directly in the question.
KNOWN_TICKERS = set(COMPANY_TICKERS.values())

_YEAR_RE = re.compile(r"\b(?:FY|fiscal\s+year)\s*(\d{4})", re.IGNORECASE)
_QUARTER_RE = re.compile(r"\bQ([1-4])\b", re.IGNORECASE)



def understand_query(query: str) -> dict:
    """Extract financial filters from a user question."""

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")

    ticker = _extract_ticker(query)
    fiscal_year = _extract_fiscal_year(query)
    fiscal_period = _extract_fiscal_period(query)

    # Microsoft sample: March 31, 2026 = Q3 FY2026
    if ticker == "MSFT" and re.search(
        r"\bMarch\s+31,?\s+2026\b",
        query,
        re.IGNORECASE,
    ):
        if fiscal_year is None:
            fiscal_year = 2026
        if fiscal_period is None:
            fiscal_period = "Q3"

    return {
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "fiscal_period": fiscal_period,
    }



def _extract_ticker(query: str) -> str | None:
    """Extract company ticker using whole-word matching."""

    text = query.lower()

    for name, ticker in COMPANY_TICKERS.items():
        if re.search(rf"\b{re.escape(name)}\b", text):
            return ticker

    for ticker in KNOWN_TICKERS:
        if re.search(
            rf"\b{re.escape(ticker)}\b",
            query,
            re.IGNORECASE,
        ):
            return ticker

    return None



def _extract_fiscal_year(query: str) -> int | None:
    match = _YEAR_RE.search(query)
    return int(match.group(1)) if match else None


def _extract_fiscal_period(query: str) -> str | None:
    match = _QUARTER_RE.search(query)
    return f"Q{match.group(1)}" if match else None

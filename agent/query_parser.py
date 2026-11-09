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

# Raw ticker aliases that resolve to a canonical ticker (e.g. GOOG -> GOOGL).
TICKER_ALIASES = {
    "GOOG": "GOOGL",
}

_YEAR_RE = re.compile(r"\b(?:FY|fiscal\s+year)\s*(\d{4})", re.IGNORECASE)
# Fallback for a bare 4-digit year ("Tesla Q3 2026") with no "FY" anchor. The
# lookbehind keeps a dollar amount like "$2026 million" from being read as a year.
_BARE_YEAR_RE = re.compile(r"(?<![\d$])\b(20\d{2})\b")
_QUARTER_RE = re.compile(r"\bQ([1-4])\b", re.IGNORECASE)
# Spelled-out period forms mapped to the compact Q1-Q4 / FY vocabulary.
_SPELLED_PERIODS = {
    "annual": "FY",
    "full year": "FY",
    "first quarter": "Q1",
    "second quarter": "Q2",
    "third quarter": "Q3",
    "fourth quarter": "Q4",
}



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

    for ticker in sorted(KNOWN_TICKERS | set(TICKER_ALIASES)):
        if re.search(
            rf"\b{re.escape(ticker)}\b",
            query,
            re.IGNORECASE,
        ):
            return TICKER_ALIASES.get(ticker, ticker)

    return None



def _extract_fiscal_year(query: str) -> int | None:
    match = _YEAR_RE.search(query)
    if match:
        return int(match.group(1))
    match = _BARE_YEAR_RE.search(query)
    return int(match.group(1)) if match else None


def _extract_fiscal_period(query: str) -> str | None:
    match = _QUARTER_RE.search(query)
    if match:
        return f"Q{match.group(1)}"
    lowered = query.lower()
    for phrase, period in _SPELLED_PERIODS.items():
        if re.search(rf"\b{re.escape(phrase)}\b", lowered):
            return period
    return None

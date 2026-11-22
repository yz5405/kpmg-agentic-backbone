"""Minimal LLM-assisted query understanding with local validation and rule-based fallback."""

import json
import os

from agent.llm_client import ChatCompletionClient
from agent.query_parser import COMPANY_TICKERS, KNOWN_TICKERS, understand_query


QUESTION_TYPES = {
    "metric_lookup",
    "relationship",
    "structured_lookup",
    "comparison",
    "unknown",
}

SYSTEM_PROMPT = """Extract financial query parameters from the user's question.

Return JSON with exactly:
company, ticker, tickers, form, fiscal_year, fiscal_period, question_type.

Rules:
- ticker must be a supported ticker for a single-company question, otherwise null.
- tickers must be a JSON list of supported tickers when one or more companies are identifiable; otherwise [].
- form may be 10-K, 10-Q, or null.
- fiscal_year must be a 4-digit integer or null.
- fiscal_period must be Q1, Q2, Q3, Q4, FY, or null.
- question_type must be one of:
  metric_lookup, relationship, structured_lookup, comparison, unknown.
Do not invent unsupported companies or periods.
"""


def _validate(parsed: dict) -> dict:
    if not isinstance(parsed, dict):
        raise ValueError("LLM query result must be a JSON object")

    ticker = parsed.get("ticker")
    if ticker is not None:
        if not isinstance(ticker, str):
            raise ValueError("ticker must be string or null")
        ticker = ticker.upper()
        if ticker not in KNOWN_TICKERS:
            raise ValueError("unsupported ticker")

    tickers = parsed.get("tickers") or []
    if not isinstance(tickers, list):
        raise ValueError("tickers must be a list")

    normalized_tickers = []
    for item in tickers:
        if not isinstance(item, str):
            raise ValueError("each ticker must be a string")
        item = item.upper()
        if item not in KNOWN_TICKERS:
            raise ValueError("unsupported ticker")
        if item not in normalized_tickers:
            normalized_tickers.append(item)

    if ticker and ticker not in normalized_tickers:
        normalized_tickers.insert(0, ticker)

    if len(normalized_tickers) == 1:
        ticker = normalized_tickers[0]
    elif len(normalized_tickers) > 1:
        ticker = None

    fiscal_year = parsed.get("fiscal_year")
    if fiscal_year is not None:
        if type(fiscal_year) is not int or not (1900 <= fiscal_year <= 2100):
            raise ValueError("invalid fiscal_year")

    fiscal_period = parsed.get("fiscal_period")
    if fiscal_period is not None:
        if fiscal_period not in {"Q1", "Q2", "Q3", "Q4", "FY"}:
            raise ValueError("invalid fiscal_period")

    form = parsed.get("form")
    if form is not None and form not in {"10-K", "10-Q"}:
        raise ValueError("invalid form")

    question_type = parsed.get("question_type", "unknown")
    if question_type not in QUESTION_TYPES:
        raise ValueError("invalid question_type")

    return {
        "ticker": ticker,
        "tickers": normalized_tickers,
        "fiscal_year": fiscal_year,
        "fiscal_period": fiscal_period,
        "form": form,
        "question_type": question_type,
        "query_understanding_mode": "llm",
    }


def understand_query_llm(query: str) -> dict:
    """Use a real LLM when enabled; otherwise fall back to the existing parser."""

    if os.getenv("KPMG_QUERY_LLM_ENABLED") != "1":
        return {
            **understand_query(query),
            "form": None,
            "question_type": "unknown",
            "query_understanding_mode": "rule_based",
        }

    try:
        client = ChatCompletionClient(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            timeout=float(os.getenv("KPMG_QUERY_LLM_TIMEOUT", "60")),
        )
        model = os.getenv("KPMG_QUERY_LLM_MODEL", os.getenv("KPMG_ANSWER_MODEL", ""))

        completion = client.complete(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
        )

        parsed = json.loads(completion.content)
        return _validate(parsed)

    except Exception:
        return {
            **understand_query(query),
            "form": None,
            "question_type": "unknown",
            "query_understanding_mode": "rule_based_fallback",
        }

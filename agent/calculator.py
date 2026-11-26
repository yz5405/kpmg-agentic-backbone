"""Arithmetic over verified, verbatim SEC revenue inputs."""

from decimal import Decimal


def calculate(rows, operation, tickers):
    if operation not in {"yoy", "difference"} or len(tickers) != (1 if operation == "yoy" else 2):
        return None
    selected = []
    for ticker in tickers:
        matches = [row for row in rows if row["metadata"]["ticker"] == ticker]
        if not matches:
            return None
        facts = [row["metadata"]["verified_financial_input"] for row in matches]
        fact = facts[0]
        keys = ("metric", "scope", "unit", "duration_months", "period_end", "comparative_period_end",
                "as_reported", "comparative_as_reported")
        if any(any(other[key] != fact[key] for key in keys) for other in facts):
            return None
        if any(fact[key] not in matches[0]["text"] for key in keys[-2:]):
            return None
        selected.append((ticker, fact, matches[0]))
    first = selected[0][1]

    def amount(value):
        return Decimal(value.replace("$", "").replace(",", "").strip())

    current = amount(first["as_reported"])
    if operation == "yoy":
        prior = amount(first["comparative_as_reported"])
        if prior <= 0:
            return None
        value = (current - prior) / prior * 100
        answer = (f"{selected[0][0]} revenue grew {value:.1f}% year over year, from "
                  f"{prior:,} to {current:,} {first['unit']} "
                  f"({first['comparative_period_end']} to {first['period_end']}).")
    else:
        second = selected[1][1]
        if any(first[key] != second[key] for key in keys[:4]):
            return None
        previous = amount(second["as_reported"])
        answer = (f"{selected[0][0]} reported {current:,} {first['unit']} for the quarter ended "
                  f"{first['period_end']}. {selected[1][0]} reported {previous:,} {second['unit']} "
                  f"for the quarter ended {second['period_end']}. The absolute difference was "
                  f"{abs(current - previous):,} {first['unit']}.")
    citations = []
    for _, fact, row in selected:
        citations.append({**row["metadata"], "text": row["text"]})
        if caption := fact.get("caption_chunk_id"):
            citations[-1]["caption_chunk_id"] = caption
    return {"answer": answer, "citations": citations}

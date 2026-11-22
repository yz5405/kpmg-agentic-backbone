"""Verify the real DuckDB store through the upstream GraphRAG contract."""
from graphrag.backends import structured_search

query = "What was the total revenue?"
filters = {"ticker": "MSFT", "form": "10-Q", "fiscal_year": 2026, "fiscal_period": "Q3"}
rows = structured_search(query, filters, top_k=15, trace_id="check-duckdb-quarter")
assert rows and all(x["ticker"] == "MSFT" and x["form"] == "10-Q" for x in rows)
facts = {x["metadata"]["fact_id"] for x in rows}
assert any(x["reporting_period_end"] == "2026-03-31" for x in rows)
for key, value in (("ticker", "AAPL"), ("fiscal_year", 2023), ("fiscal_period", "Q2")):
    changed = structured_search(query, {**filters, key: value}, top_k=15)
    assert facts.isdisjoint(x["metadata"]["fact_id"] for x in changed)
    print(key, value, "disjoint", len(changed))
many = structured_search(query, {**filters, "ticker": ["MSFT", "AAPL"]}, top_k=30)
assert many and {x["ticker"] for x in many} <= {"MSFT", "AAPL"}
print("Multi-company observed:", sorted({x["ticker"] for x in many}))
try:
    structured_search(query, {"ticker": "MSFT", "fiscal_period": "Q3"})
except ValueError as exc:
    assert "fiscal_period needs fiscal_year" in str(exc)
    print("Quarter without fiscal year: refused")
else:
    raise AssertionError("Quarter without fiscal year was accepted")

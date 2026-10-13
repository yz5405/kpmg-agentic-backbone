
# Agentic Backbone — Function Contracts v0.1

Project: KPMG Financial Document Q&A

Target MVP: October 22, 2026

Implementation: Plain Python, rule-based, no LLM API.

## Module 1 — Query Understanding

**Owner:** Member 1

**File:** `agent/query_parser.py`

### Function Signature

```python
def understand_query(query: str) -> dict:
    """Extract financial filters from a user question."""
```

### Input
- `query`: str — Original user question.

### Output
A dictionary containing exactly these required keys:

- `ticker`: str | None
- `fiscal_year`: int | None
- `fiscal_period`: str | None

### Example

Input:

`"What was Microsoft's revenue in Q3 FY2026?"`

Output:

```python
{
    "ticker": "MSFT",
    "fiscal_year": 2026,
    "fiscal_period": "Q3"
}
```

### Requirements

1. Use rule-based parsing only.
2. Extract supported company names/tickers.
3. Extract fiscal year and fiscal quarter when available.
4. Return None for fields that cannot be extracted.
5. Always return all three keys.
6. Do not call the RAG retriever.
7. Do not mutate AgentState.
8. Do not call an LLM API.

### State Integration

The workflow will call:

```python
state.filters = understand_query(state.query)
```

### Acceptance Tests

**Case 1: Complete filters**

Input: `"Microsoft Q3 FY2026"`

Expected:
```python
{"ticker": "MSFT", "fiscal_year": 2026, "fiscal_period": "Q3"}
```

**Case 2: Partial filters**

Input: `"Microsoft FY2025"`

Expected:
```python
{"ticker": "MSFT", "fiscal_year": 2025, "fiscal_period": None}
```

**Case 3: No recognizable filters**

Input: `"Revenue performance"`

Expected:
```python
{"ticker": None, "fiscal_year": None, "fiscal_period": None}
```

### Error Handling

- Valid string inputs without recognizable filters return None values.
- Empty or non-string input raises ValueError.
- Workflow-level error routing is handled separately.

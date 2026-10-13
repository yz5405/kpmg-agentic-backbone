
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


---

## Module 2 — RAG Tool Integration

**Owner:** Member 2

**File:** `agent/tools/rag_tool.py`

### Function Signature

```python
def retrieve_evidence(
    query: str,
    filters: dict | None = None,
    top_k: int = 10
) -> list[dict]:
    """Retrieve and normalize evidence from the RAG tool."""
```

### Upstream RAG Contract

The RAG Team provides the following agreed interface:

```python
retrieve(
    query: str,
    filters: dict | None = None,
    top_k: int = 10
) -> list[RetrievedChunk]
```

### Input

- `query`: Original user question.
- `filters`: Financial filters extracted by query_parser.py.
- `top_k`: Maximum number of evidence chunks.

### Output

Return a list of normalized evidence dictionaries.

Proposed internal evidence structure:

```python
[
    {
        "text": "Example financial filing excerpt...",
        "metadata": {
            "ticker": "MSFT",
            "fiscal_year": 2026,
            "fiscal_period": "Q3",
            "source": "10-Q"
        }
    }
]
```

The exact RetrievedChunk fields must be confirmed
with the RAG Team before implementing the adapter.

### Requirements

1. Use the existing RAG Mock Retriever for MVP.
2. Do not implement a new retrieval engine.
3. Accept query, filters, and top_k.
4. Return normalized evidence dictionaries.
5. Preserve available source metadata.
6. Return an empty list if no evidence is found.
7. Raise ValueError if top_k <= 0.
8. Propagate unexpected retrieval errors.
9. Do not generate an LLM answer.
10. Do not modify AgentState directly.

### State Integration

The workflow will call:

```python
state.evidence = retrieve_evidence(
    query=state.query,
    filters=state.filters,
    top_k=state.top_k
)
```

### Acceptance Tests

**Case 1: Successful Retrieval**

Input: Microsoft Q3 FY2026

Expected:
- Returns a non-empty list.
- Each evidence item contains text and metadata.
- Available source metadata is preserved.

**Case 2: No Evidence**

Input: Microsoft FY2025

Expected (using the agreed MVP mock fixture):
```python
[]
```

**Case 3: Invalid top_k**

Input: top_k = 0

Expected:
```python
ValueError
```

### Error Handling

- Non-empty evidence list: workflow may route to SUCCESS.
- Empty evidence list: workflow routes to NO_EVIDENCE.
- Invalid top_k or retrieval exception: workflow handles ERROR.

The adapter raises exceptions but does not set
workflow status itself.

### RAG Team Coordination

Before real retriever integration, confirm:

1. RetrievedChunk field names and types.
2. Available source metadata fields.
3. Python import path and dependencies.
4. Whether filtering supports ticker, fiscal_year,
   and fiscal_period.
```



---

## Module 3 — Conditional Routing

**Owner:** Member 3

**File:** `agent/routing.py`

### Function Signature

```python
from agent.state import AgentState

def route_result(state: AgentState) -> AgentState:
    """Determine workflow status from evidence and errors."""
```

### Input

- `state`: AgentState object containing retrieval results.

Relevant state fields:
- `state.evidence`
- `state.error`
- `state.status`

### Output

Return the same AgentState object with an updated status.

Allowed final statuses:
- SUCCESS
- NO_EVIDENCE
- ERROR

### Routing Rules

1. If state.error is not None:
   - Set status to ERROR.

2. Otherwise, if state.evidence contains one or more items:
   - Set status to SUCCESS.

3. Otherwise:
   - Set status to NO_EVIDENCE.

4. Do not modify query, filters, top_k, or evidence.

5. Do not call the RAG tool or LLM API.

### Workflow Integration

The workflow will call:

```python
state = route_result(state)
```

If query parsing or retrieval raises an exception,
workflow.py is responsible for capturing it:

```python
try:
    # Query parsing and retrieval
    ...
except Exception as exc:
    state.error = str(exc)

state = route_result(state)
```

### Acceptance Tests

**Case 1: Success**

Input:
```python
state.evidence = [
    {"text": "Revenue evidence", "metadata": {"source": "10-Q"}}
]
state.error = None
```

Expected:
```python
state.status == "SUCCESS"
```

**Case 2: No Evidence**

Input:
```python
state.evidence = []
state.error = None
```

Expected:
```python
state.status == "NO_EVIDENCE"
```

**Case 3: Error**

Input:
```python
state.error = "top_k must be greater than zero"
state.evidence = []
```

Expected:
```python
state.status == "ERROR"
```

**Case 4: Error Takes Priority**

Input:
```python
state.error = "Retrieval failed"
state.evidence = [{"text": "Partial evidence", "metadata": {}}]
```

Expected:
```python
state.status == "ERROR"
```

### Error Handling

- Routing does not catch retrieval exceptions.
- Routing does not create error messages.
- If state.error is present, ERROR takes priority.
- Routing only updates state.status.
- The same AgentState instance is returned.

### State Ownership

Owned field:
- `state.status`

Read-only fields:
- `state.evidence`
- `state.error`

Other AgentState fields must remain unchanged.
```


---

## Module 4 — State Management & Execution Logging

**Owner:** Member 4

**Files:**
- `agent/state.py`
- `agent/logging_utils.py`

### Shared State

The shared AgentState structure was defined and tested
by Team Leads in Step 2.

Member 4 must preserve the existing AgentState fields
and create_initial_state() interface.

Any schema change requires Team Lead approval.

### Function Signature

```python
from agent.state import AgentState

def log_event(
    state: AgentState,
    message: str,
    level: str = "INFO"
) -> None:
    """Append a formatted execution log to AgentState."""
```

### Input

- `state`: Shared AgentState object.
- `message`: Description of an execution event.
- `level`: Log severity, default INFO.

### Output

Returns None.

Appends one formatted string to state.logs.

### Supported Levels

- INFO
- WARNING
- ERROR

### Example

```python
state = create_initial_state("Microsoft Q3 FY2026")

log_event(state, "Query parsing started")

assert state.logs == [
    "[INFO] Query parsing started"
]
```

### Requirements

1. Use Python standard library only.
2. Append messages to state.logs in execution order.
3. Format logs as "[LEVEL] message".
4. Default level is INFO.
5. Accept INFO, WARNING, and ERROR.
6. Normalize lowercase log levels to uppercase.
7. Raise ValueError for unsupported levels.
8. Do not modify any other AgentState fields.
9. Do not log API keys, credentials, or sensitive data.
10. Do not implement persistent storage or session memory.

### State Ownership

Member 4 owns:
- state.logs

Member 4 maintains but must not independently redesign:
- AgentState schema
- create_initial_state()

Member 4 does not own:
- state.filters
- state.evidence
- state.status
- state.error

### Workflow Integration

```python
log_event(state, "Query parsing started")

state.filters = understand_query(state.query)

log_event(state, "Query parsing completed")
```

The workflow is responsible for deciding
when logging functions are called.

### Acceptance Tests

**Case 1: Default INFO**

```python
log_event(state, "Workflow started")

assert state.logs[-1] == "[INFO] Workflow started"
```

**Case 2: ERROR Logging**

```python
log_event(state, "Retrieval failed", level="ERROR")

assert state.logs[-1] == "[ERROR] Retrieval failed"
```

**Case 3: Lowercase Level**

```python
log_event(state, "No evidence found", level="warning")

assert state.logs[-1] == "[WARNING] No evidence found"
```

**Case 4: Invalid Level**

```python
import pytest

with pytest.raises(ValueError):
    log_event(state, "Test", level="DEBUG")
```

**Case 5: State Independence**

Logs recorded for one AgentState must not
appear in a separate AgentState instance.

### Error Handling

- Unsupported log level raises ValueError.
- Logging errors are not silently ignored.
- Logging does not determine workflow status.
- Workflow-level exceptions are handled by workflow.py.
```

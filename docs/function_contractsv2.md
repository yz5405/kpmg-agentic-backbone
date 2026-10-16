
# Agentic Backbone — Function Contracts v0.2

**Project:** Columbia QMSS × KPMG Financial Document Q&A  
**Updated:** October 15, 2026  
**Target MVP:** October 22, 2026  
**Target Framework:** LangGraph + Python  
**Future Direction:** Hierarchical Multi-Agent Architecture  
**Current Status:** LangChain mock workflow tested; LangGraph migration and real RAG integration pending.

---

## 1. Purpose and Development Scope

This document defines the function contracts for the five Agentic Backbone modules.

Following KPMG's feedback on October 15, our team is moving toward a LangGraph-based orchestration architecture, with future support for hierarchical multi-agent workflows.

The October 22 MVP will focus on:

1. Query understanding
2. RAG tool integration
3. Conditional routing
4. Shared state and execution logging
5. Automated testing
6. LangGraph workflow orchestration

The MVP should support a complete question-to-evidence workflow.

**Not required for October 22:**

- Multiple autonomous LLM agents
- LLM answer generation
- Live GraphRAG retrieval
- SQL tool integration
- Persistent conversation memory
- Production frontend/backend deployment

### Development Rules

1. Each member owns one module and its defined public functions.
2. Team Leads own the main LangGraph `StateGraph`.
3. Modules must remain independently testable.
4. Functions should not directly depend on the complete graph.
5. Members may use LangGraph where appropriate.
6. Changes to shared contracts must be approved by Team Leads.
7. Do not commit API keys, credentials, or sensitive data.
8. Preserve existing functionality during the LangGraph migration.

---

## 2. LangGraph Integration Principles

LangGraph will orchestrate reusable Python functions.

The main workflow will use:

- `StateGraph`
- Nodes
- Edges
- Conditional Edges
- Shared State
- Execution Logging

### Core Design Principle

**Module functions and graph orchestration are separate responsibilities.**

Members implement reusable business logic.

Team Leads integrate that logic into LangGraph nodes and connect the nodes into the main workflow.

For example:

```python
def understand_query(query: str) -> dict:
    # Implemented by Member 1
    ...

def query_node(state: dict) -> dict:
    # LangGraph wrapper maintained by Team Leads
    filters = understand_query(state["query"])
    return {"filters": filters}
```

This separation makes modules easier to test, maintain, and reuse in future multi-agent workflows.

### LangGraph Node Contract

The main graph will use a dictionary-based state.

Node functions should:

1. Accept the current graph state.
2. Execute their assigned operation.
3. Return only the state fields they update.
4. Avoid unnecessary mutation of unrelated fields.
5. Allow the workflow to record errors and execution events.

The Team Leads will implement the final node wrappers in `agent/workflow.py`.

---

## 3. Shared State Contract

**Owners:** Team Leads (schema), Lingfei Zhang (logging and state support)

**File:** `agent/state.py`

The existing v0.1 `AgentState` is a Python dataclass.

For LangGraph v0.2, the main graph will use a `TypedDict`-compatible state schema.

This is a planned migration and is not yet implemented.

### Target LangGraph State

```python
from typing import Any, TypedDict

class AgentGraphState(TypedDict):
    query: str
    filters: dict[str, Any]
    top_k: int
    evidence: list[dict[str, Any]]
    status: str
    error: str | None
    logs: list[str]
```

### Required Fields

| Field | Type | Description |
|---|---|---|
| query | str | Original financial question |
| filters | dict | Parsed financial filters |
| top_k | int | Maximum retrieval results |
| evidence | list[dict] | Retrieved evidence and metadata |
| status | str | Workflow execution status |
| error | str or None | Error information |
| logs | list[str] | Ordered execution logs |

### Status Constants

- `PENDING`
- `SUCCESS`
- `NO_EVIDENCE`
- `ERROR`

### State Initialization

Team Leads will maintain an initializer with the following behavior:

```python
def create_initial_state(
    query: str,
    top_k: int = 10
) -> dict:
    return {
        "query": query,
        "filters": {},
        "top_k": top_k,
        "evidence": [],
        "status": "PENDING",
        "error": None,
        "logs": []
    }
```

### Migration Rules

1. Preserve the original seven core state fields.
2. Do not independently redesign the state schema.
3. The existing dataclass can remain temporarily for backward compatibility.
4. Team Leads will decide when the main workflow switches to `AgentGraphState`.
5. Avoid mixing dataclass attribute access and dictionary access inside the same node.
6. Every test invocation must use a fresh state.
7. Never store credentials in state or logs.

### Important: Logging State Updates

LangGraph nodes should not rely on mutating a shared state object in place.

The main graph should return explicit state updates.

For the MVP, `logs` will be a standard list field. Each node wrapper must return the complete updated log list when appending entries.

This avoids unexpected behavior when state updates are merged.

Future versions may use reducers for parallel agent execution.

---

## 4. Module 1 — Query Understanding

**Owner:** Jixuan Liu  
**File:** `agent/query_parser.py`

### Function Signature

```python
def understand_query(query: str) -> dict:
    """Extract financial filters from a user question."""
```

### Input

- `query`: Original user financial question.

### Output

Return a dictionary with exactly these required keys:

```python
{
    "ticker": str | None,
    "fiscal_year": int | None,
    "fiscal_period": str | None
}
```

Example:

**Input:**

```text
What was Microsoft's revenue in Q3 FY2026?
```

**Expected Output:**

```python
{
    "ticker": "MSFT",
    "fiscal_year": 2026,
    "fiscal_period": "Q3"
}
```

### Requirements

1. Use rule-based parsing for the October 22 MVP.
2. Recognize supported company names and tickers.
3. Extract fiscal year when present.
4. Extract fiscal quarter when present.
5. Return `None` for missing fields.
6. Always return all three required keys.
7. Do not call the Retriever.
8. Do not call an LLM API.
9. Do not modify shared workflow state.
10. Raise `ValueError` for empty or invalid input.

### LangGraph Integration

The Team Leads will implement a query node similar to:

```python
def query_node(state: AgentGraphState) -> dict:
    filters = understand_query(state["query"])

    return {
        "filters": filters
    }
```

Member 1 does not need to create a separate `StateGraph`.

### Acceptance Tests

**Case 1 — Complete Filters**

Input:

```text
Microsoft Q3 FY2026
```

Expected:

```python
{
    "ticker": "MSFT",
    "fiscal_year": 2026,
    "fiscal_period": "Q3"
}
```

**Case 2 — Partial Filters**

Input:

```text
Microsoft FY2025
```

Expected:

```python
{
    "ticker": "MSFT",
    "fiscal_year": 2025,
    "fiscal_period": None
}
```

**Case 3 — No Recognizable Filters**

Input:

```text
Revenue performance
```

Expected:

```python
{
    "ticker": None,
    "fiscal_year": None,
    "fiscal_period": None
}
```

**Case 4 — Invalid Input**

Empty or non-string input raises `ValueError`.

### Ownership Boundary

Member 1 owns financial filter extraction.

Team Leads own the LangGraph node wrapper.

---

## 5. Module 2 — RAG Tool Integration

**Owner:** Jiahui Yang  
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

### Upstream Retrieval Contract

The RAG Team provides the following interface:

```python
retrieve(
    query: str,
    filters: dict | None = None,
    top_k: int = 10
) -> list[RetrievedChunk]
```

The RAG Team has reported that its retrieval contract has been merged and that the retriever is wrapped as a LangChain tool.

The Agent Team must validate its implementation and actual output before integration.

### Input

- `query`: Financial question.
- `filters`: Parsed financial filters.
- `top_k`: Maximum retrieval results.

### Output

Return normalized evidence dictionaries.

Example internal format:

```python
[
    {
        "text": "Example filing evidence...",
        "metadata": {
            "ticker": "MSFT",
            "fiscal_year": 2026,
            "fiscal_period": "Q3",
            "source": "10-Q"
        }
    }
]
```

This is our internal normalized format, not a confirmed representation of every field returned by the upstream Retriever.

### Requirements

1. Integrate the RAG Team's existing Retriever.
2. Preserve the same public function signature.
3. Do not implement a new retrieval engine.
4. Pass financial metadata filters correctly.
5. Preserve source IDs and available citation metadata.
6. Return normalized evidence dictionaries.
7. Return an empty list if retrieval returns no results.
8. Raise `ValueError` when `top_k <= 0`.
9. Propagate unexpected retrieval exceptions.
10. Do not generate an LLM answer.
11. Do not modify shared graph state.
12. Retain a mock implementation or test fixture for deterministic testing.

### LangGraph Integration

The Team Leads will wrap the adapter in a retrieval node:

```python
def retrieval_node(state: AgentGraphState) -> dict:
    evidence = retrieve_evidence(
        query=state["query"],
        filters=state["filters"],
        top_k=state["top_k"]
    )

    return {
        "evidence": evidence
    }
```

### External Integration Checklist

Confirm with the RAG Team:

1. Python import path.
2. Required package dependencies.
3. Input parameter compatibility.
4. `RetrievedChunk` field names and data types.
5. Available citation and provenance fields.
6. Supported company and fiscal-period filters.
7. Empty-result behavior.
8. Error and timeout behavior.

### Acceptance Tests

**Case 1 — Successful Retrieval**

- Returns a non-empty evidence list.
- Every evidence item contains text and metadata.
- Available source information is preserved.

**Case 2 — No Evidence**

- Mock Retriever returns `[]`.
- Adapter returns `[]`.

**Case 3 — Invalid Parameter**

- `top_k = 0`
- Expected: `ValueError`.

**Case 4 — Upstream Failure**

- Mock Retriever raises an exception.
- Adapter propagates the exception.

**Case 5 — Metadata Preservation**

- Source IDs and available metadata remain accessible after normalization.

### Ownership Boundary

Member 2 owns the RAG adapter and normalization logic.

Team Leads own the LangGraph retrieval node and orchestration.

The RAG Team owns the retrieval engine itself.

---

## 6. Module 3 — Conditional Routing

**Owner:** Lidan Yu  
**File:** `agent/routing.py`

### Function Signature

```python
from agent.state import AgentState

def route_result(state: AgentState) -> AgentState:
    """Determine workflow status from evidence and errors."""
```

### v0.2 Compatibility Requirement

The existing function contract must remain available for the v0.1 workflow and tests during migration.

For LangGraph, Member 3 will also provide a pure routing decision function:

```python
def determine_status(
    evidence: list[dict],
    error: str | None
) -> str:
    """Return SUCCESS, NO_EVIDENCE, or ERROR."""
```

### Routing Rules

1. If `error is not None`, return `ERROR`.
2. Otherwise, if evidence is non-empty, return `SUCCESS`.
3. Otherwise, return `NO_EVIDENCE`.

Errors take priority over partial evidence.

### LangGraph Integration

Team Leads will implement a routing node:

```python
def routing_node(state: AgentGraphState) -> dict:
    status = determine_status(
        evidence=state["evidence"],
        error=state["error"]
    )

    return {
        "status": status
    }
```

Conditional edges may then use the current status:

```python
def select_outcome(state: AgentGraphState) -> str:
    return state["status"]
```

The Team Leads will define the actual `add_conditional_edges()` connections.

### Requirements

1. Keep existing routing behavior.
2. Add a reusable routing decision function.
3. Do not call RAG, GraphRAG, or SQL tools.
4. Do not call an LLM API.
5. Do not modify retrieved evidence.
6. Do not implement independent graph orchestration.
7. Return only supported status values.

### Acceptance Tests

| Evidence | Error | Expected |
|---|---|---|
| Non-empty | None | SUCCESS |
| Empty | None | NO_EVIDENCE |
| Empty | Error message | ERROR |
| Non-empty | Error message | ERROR |

### Future Multi-Agent Routing

Later versions may support routing decisions such as:

- Document retrieval
- Graph retrieval
- Structured-data retrieval
- Evidence verification
- Answer synthesis

These decisions are not part of the October 22 required routing contract.

### Ownership Boundary

Member 3 owns routing rules and decision functions.

Team Leads own conditional edges and the complete graph structure.

---

## 7. Module 4 — State Management & Execution Logging

**Owner:** Lingfei Zhang  
**Files:**
- `agent/state.py`
- `agent/logging_utils.py`

### Responsibilities

1. Maintain the existing state definitions during migration.
2. Implement execution logging.
3. Support LangGraph-compatible logging behavior.
4. Ensure logs capture execution order.
5. Avoid exposing sensitive information.

### Existing Function Contract

```python
from agent.state import AgentState

def log_event(
    state: AgentState,
    message: str,
    level: str = "INFO"
) -> None:
    """Append an execution log to the existing AgentState."""
```

This function should remain compatible with existing tests.

### New LangGraph-Compatible Logging Helper

Add a pure formatting function:

```python
def format_log_event(
    message: str,
    level: str = "INFO"
) -> str:
    """Return a formatted log entry."""
```

Expected:

```python
format_log_event("RAG retrieval started")
# "[INFO] RAG retrieval started"
```

The Team Leads will use this helper inside LangGraph nodes.

Example:

```python
def append_graph_log(
    state: AgentGraphState,
    message: str,
    level: str = "INFO"
) -> dict:
    entry = format_log_event(message, level)

    return {
        "logs": state["logs"] + [entry]
    }
```

### Supported Log Levels

- INFO
- WARNING
- ERROR

### Formatting Rules

1. Format messages as `[LEVEL] message`.
2. Convert lowercase levels to uppercase.
3. Raise `ValueError` for unsupported levels.
4. Preserve chronological execution order.
5. Avoid logging credentials or sensitive values.

### Tool Calling Sequence

KPMG specifically requested observable tool-calling sequences when using LangGraph.

At minimum, the MVP should record:

- Workflow start
- Query parsing start/completion
- Retrieval tool start/completion
- Retrieval failure, if applicable
- Routing result
- Workflow completion

Example:

```text
[INFO] Workflow started
[INFO] Query parsing started
[INFO] Query parsing completed
[INFO] RAG retrieval started
[INFO] RAG retrieval completed
[INFO] Workflow status: SUCCESS
```

These events must reflect actual execution, not hardcoded demo output.

### Requirements

1. Preserve existing logging compatibility.
2. Implement `format_log_event()`.
3. Do not independently redesign `AgentGraphState`.
4. Do not implement persistent session memory.
5. Do not independently modify the main LangGraph graph.
6. Keep logs deterministic for unit testing.
7. Coordinate state changes with Team Leads.

### Acceptance Tests

**Case 1 — INFO Formatting**

```python
assert format_log_event("Workflow started") == \
    "[INFO] Workflow started"
```

**Case 2 — ERROR Formatting**

```python
assert format_log_event(
    "Retrieval failed", "ERROR"
) == "[ERROR] Retrieval failed"
```

**Case 3 — Lowercase Level**

```python
assert format_log_event(
    "No evidence", "warning"
) == "[WARNING] No evidence"
```

**Case 4 — Invalid Level**

Unsupported level raises `ValueError`.

**Case 5 — State Isolation**

Logs from one workflow execution must not leak into another.

**Case 6 — Execution Order**

Log entries must follow the actual order of executed workflow steps.

### Ownership Boundary

Member 4 owns logging utilities and state support.

Team Leads own the final LangGraph state schema and workflow-level logging integration.

---

## 8. Module 5 — Testing & Quality Assurance

**Owner:** Yichen Liu  
**Directory:** `tests/`

### Objective

Validate module contracts and end-to-end workflow behavior.

Testing must cover both existing Python modules and the new LangGraph workflow.

### Testing Framework

Use `pytest`.

Run from the repository root:

```bash
python -m pytest tests/ -v
```

### Required Test Files

- `tests/test_query_parser.py`
- `tests/test_rag_tool.py`
- `tests/test_routing.py`
- `tests/test_logging.py`
- `tests/test_workflow.py`

Keep existing `tests/test_skeleton.py`.

### Module Tests

**Query Understanding**

- Complete filters
- Partial filters
- Unknown filters
- Invalid input

**RAG Adapter**

- Successful retrieval
- Empty result
- Invalid `top_k`
- Retriever exceptions
- Metadata preservation

**Routing**

- SUCCESS
- NO_EVIDENCE
- ERROR
- Error priority

**Logging**

- INFO formatting
- ERROR formatting
- Level normalization
- Invalid levels
- Execution order
- State isolation

### LangGraph Integration Tests

Coordinate with Team Leads to test:

1. Correct graph entry point.
2. Expected node execution sequence.
3. Proper state updates between nodes.
4. Correct conditional routing.
5. Final output structure.
6. Error handling.
7. Execution logs.
8. No cross-run state contamination.

### Minimum End-to-End Scenarios

**Scenario 1 — SUCCESS**

Input:

```text
Microsoft Q3 FY2026
```

Expected:

- Financial filters extracted
- Mock evidence returned
- Source metadata preserved
- Status = SUCCESS
- Execution logs recorded

**Scenario 2 — NO_EVIDENCE**

Use a deterministic mock fixture that returns no evidence.

Expected:

- Empty evidence list
- Status = NO_EVIDENCE
- Workflow completes without crashing

**Scenario 3 — ERROR**

Input:

```text
top_k = 0
```

Expected:

- Retrieval validation fails
- Error message recorded
- Status = ERROR

### Real RAG Integration Test

When the RAG Team's Retriever is available, add a separate integration test.

Verify:

1. Real Retriever can be imported.
2. Financial filters are accepted.
3. Evidence fields can be normalized.
4. Source metadata is preserved.
5. Workflow returns the expected structure.

Real integration tests may require external dependencies.

They should be separated from deterministic mock tests so that regular unit tests remain reproducible.

### Development Rules

1. Use pytest.
2. Keep mock tests deterministic.
3. Do not hardcode test success.
4. Do not modify production modules without approval.
5. Report interface mismatches to Team Leads.
6. Retain existing working tests during migration.
7. Add LangGraph integration tests after the workflow is available.
8. Do not require LLM API credentials for MVP tests.

### Acceptance Criteria

- Module unit tests pass.
- Three MVP workflow scenarios pass.
- Correct LangGraph execution is verified.
- Source metadata is preserved.
- Logs reflect actual tool-calling order.
- Mock tests run without external API credentials.

---

## 9. Team Lead Responsibilities

**Owners:** Agentic Backbone Team Leads

**Files:**
- `agent/workflow.py`
- `agent/state.py` (final schema approval)
- `main.py`
- `requirements.txt`

### Responsibilities

1. Maintain the overall architecture.
2. Implement the main LangGraph `StateGraph`.
3. Create node wrappers for member functions.
4. Define workflow edges and conditional edges.
5. Coordinate shared-state updates.
6. Integrate RAG retrieval.
7. Implement workflow-level exception handling.
8. Connect execution logging.
9. Review and merge member pull requests.
10. Run end-to-end tests.
11. Prepare the October 22 demo.

### Main Workflow Interface

Preserve the public entry point:

```python
def run_agent(
    query: str,
    top_k: int = 10
):
    """Execute the financial retrieval workflow."""
```

The final return type will be a LangGraph-compatible state dictionary.

The previous dataclass-based workflow may be retained temporarily for backward compatibility.

### LangGraph Graph Structure

The initial workflow should conceptually follow:

```text
START
  |
Query Understanding
  |
RAG Retrieval
  |
Conditional Routing
  |
  +-- SUCCESS ------> END
  |
  +-- NO_EVIDENCE --> END
  |
  +-- ERROR --------> END
```

Node wrappers and exception handling must ensure failures are reflected in graph state.

A node should not allow an unhandled retrieval exception to terminate the entire graph without recording the failure when that failure is expected to become an ERROR result.

### Dependency Management

Team Leads will update `requirements.txt` for LangGraph.

Do not remove existing dependencies until migration tests pass.

---

## 10. Cross-Team Dependencies

### RAG Team

**Priority: High**

Required:

- Callable Retriever
- Import instructions
- RetrievedChunk schema
- Metadata filtering behavior
- Source IDs and citations
- Sample financial question

Expected outcome:

A real retrieval call can be executed through our RAG adapter.

### GraphRAG Team

**Priority: Planning**

Required:

- Planned graph retrieval interface
- Supported entity / relationship queries
- Evidence format
- Abstention and missing-relationship behavior

Expected outcome:

Future GraphRAG integration requirements documented.

Live GraphRAG is not required for October 22.

### Business / UI Team

**Priority: Interface Alignment**

Required:

- User question request format
- Evidence and citation display requirements
- Error / no-evidence representation
- Future answer-generation requirements

Expected outcome:

A proposed UI-to-Agent request / response contract.

Complete UI integration is not required for October 22.

### Evaluation Team

**Priority: Testing Alignment**

Required:

- Shared test questions
- Expected evidence format
- Citation requirements
- No-answer cases
- Relevant evaluation metrics

Expected outcome:

Consistent workflow and retrieval test definitions.

---

## 11. October 22 Deliverables

The minimum acceptable MVP should demonstrate:

1. A user submits a financial question.
2. The workflow extracts relevant financial filters.
3. The Agent calls a Retriever.
4. The Retriever returns evidence or an empty result.
5. The workflow handles success, no evidence, and errors.
6. Source metadata remains available.
7. Execution logs show actual processing steps.
8. The final result can be inspected.
9. Automated tests pass.

### Preferred Demo

Use the actual RAG Team Retriever with real SEC evidence.

### Fallback Demo

Use deterministic mock retrieval if cross-team integration is not yet stable.

The team must clearly distinguish mock results from real SEC evidence.

### Out of Scope for October 22

- Complete hierarchical multi-agent execution
- GraphRAG production integration
- SQL tools
- LLM-generated financial answers
- Full UI deployment
- Persistent chat sessions

---

## 12. Development Timeline

| Date | Task | Deliverable |
|---|---|---|
| Oct 15–16 | Architecture and contract revision | Updated documentation |
| Oct 19 | Module development | Five initial module PRs |
| Oct 20 | Workflow integration | First end-to-end workflow |
| Oct 21 | Testing and debugging | Regression test results |
| Oct 22 | MVP presentation | Working LangGraph-based demo |

---

## 13. Future Multi-Agent Extensions

The long-term architecture may include:

- Supervisor Agent
- RAG Retrieval Agent
- GraphRAG Retrieval Agent
- Structured Data / SQL Agent
- Answer Synthesis Agent

Potential future state fields:

- `selected_tools`
- `agent_messages`
- `tool_results`
- `answer`
- `citations`
- `execution_trace`

Potential future capabilities:

1. Hierarchical task delegation
2. Multi-tool retrieval
3. Evidence aggregation
4. Evidence sufficiency evaluation
5. Citation validation
6. Grounded LLM answer generation
7. Abstention
8. Multi-agent observability

Future additions require updated function contracts and acceptance tests.

They should not be implemented independently without an agreed architecture.

---

## 14. Final Development Principles

1. Build a stable MVP before adding complexity.
2. Use LangGraph for orchestration, not to duplicate module logic.
3. Keep Python module functions independently testable.
4. Let Team Leads maintain the main graph.
5. Allow members to learn and experiment with LangGraph.
6. Preserve evidence provenance and citation metadata.
7. Make tool-calling sequences observable.
8. Distinguish missing evidence from execution errors.
9. Prefer reusable interfaces over hardcoded demo behavior.
10. Coordinate all contract changes before integration.

---

## 15. Current Implementation Status

**Completed:**

- GitHub repository structure
- Initial module contracts
- Original shared-state dataclass
- LangChain Core workflow skeleton
- Mock retrieval tests

**In Progress / Planned:**

- LangGraph StateGraph implementation
- TypedDict-based shared state
- Updated routing and logging support
- Five member module implementations
- Real RAG integration
- LangGraph integration tests

**Future Scope:**

- Hierarchical Multi-Agent
- GraphRAG integration
- SQL retrieval tools
- LLM answer synthesis
- Production UI integration

**This document defines target interfaces. It does not imply that all LangGraph components have already been implemented.**

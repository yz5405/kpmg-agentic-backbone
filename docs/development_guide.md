
# Agentic Backbone — Development Guide v0.1

**Project:** Columbia University QMSS x KPMG Practicum  
**Team:** Agentic Backbone / Agents & AI Workflows  
**Framework:** LangChain Core + Plain Python  
**Module Submission Deadline:** October 19, 2026  
**Working MVP Demo:** October 22, 2026

---

## 1. Project Overview

Our team is building a rule-based single-agent workflow
for financial document retrieval.

The workflow follows:

User Query
→ Query Understanding
→ RAG Retrieval
→ Conditional Routing
→ Evidence Output

The current MVP uses LangChain RunnableLambda and LCEL
for orchestration.

No LLM API key, GraphRAG, SQL, or Multi-Agent
implementation is required.

## 2. Team Assignments

| Member | Workstream | Files |
|---|---|---|
| Jixuan Liu | Query Understanding | agent/query_parser.py |
| Jiahui Yang | RAG Tool Integration | agent/tools/rag_tool.py |
| Lidan Yu | Conditional Routing | agent/routing.py |
| Lingfei Zhang | State & Logging | agent/logging_utils.py |
| Yichen Liu | Testing & QA | tests/ |

The AgentState schema in agent/state.py is already
defined and tested.

Changes to the AgentState schema require
Team Lead approval.

Team Leads own:
- agent/workflow.py
- main.py
- docs/architecture.md
- docs/function_contracts.md
- Final integration and PR reviews

## 3. Required Reading

Before implementation, please review:

1. docs/architecture.md
2. docs/function_contracts.md
3. agent/state.py
4. agent/workflow.py

All modules must follow the approved function contracts.

Do not independently change function signatures,
return types, or shared state fields.

## 4. GitHub Collaboration Rules

Repository:
https://github.com/yz5405/kpmg-agentic-backbone

Default branch: main

Each member must create a separate feature branch.

| Member | Branch |
|---|---|
| Jixuan Liu | feature/query-parser |
| Jiahui Yang | feature/rag-tool |
| Lidan Yu | feature/routing |
| Lingfei Zhang | feature/logging |
| Yichen Liu | test/qa |

### Rules

1. Do not commit directly to main.
2. Create your branch from the latest main.
3. Only modify assigned files unless approved.
4. Do not change function contracts independently.
5. Commit changes to your own branch.
6. Open a Pull Request targeting main.
7. Team Leads review code before merging.
8. Coordinate any cross-module changes in advance.

If repository write access has not been granted,
request collaborator access from the Team Leads.

## 5. How to Create a Branch on GitHub

For members using the GitHub website:

1. Open the repository.
2. Select the main branch dropdown.
3. Enter your assigned branch name.
4. Click "Create branch".
5. Confirm the new branch is selected.
6. Navigate to your assigned Python file.
7. Click Edit and implement your module.
8. Commit changes to your feature branch.

Before committing, confirm that the selected
branch is NOT main.

## 6. Python Development Setup

Recommended: Python 3.10 or newer.

Clone the repository:

```bash
git clone https://github.com/yz5405/kpmg-agentic-backbone.git
cd kpmg-agentic-backbone
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Run baseline tests:

```bash
python -m pytest tests/ -v
```

Alternatively, use Google Colab to clone
the repository and install requirements.

When using Colab, ensure that the checked-out
branch contains your latest code.

The existing workflow tests use mocked modules.
Passing them alone does not prove your own module
implementation is correct.

## 7. Module Development Requirements

### Member 1 — Query Understanding

File: agent/query_parser.py

Implement:

```python
def understand_query(query: str) -> dict:
    ...
```

Must extract:
- ticker
- fiscal_year
- fiscal_period

Return None for unrecognized fields.

Use rule-based parsing only.

### Member 2 — RAG Tool Integration

File: agent/tools/rag_tool.py

Implement:

```python
def retrieve_evidence(
    query: str,
    filters: dict | None = None,
    top_k: int = 10
) -> list[dict]:
    ...
```

Requirements:
- Integrate the agreed mock retriever.
- Preserve available source metadata.
- Return [] when no evidence is found.
- Raise ValueError for invalid top_k.
- Do not implement a new retrieval engine.

Confirm RetrievedChunk schema and import path
with the RAG Team before implementing the adapter.

### Member 3 — Conditional Routing

File: agent/routing.py

Implement:

```python
def route_result(state: AgentState) -> AgentState:
    ...
```

Routing priority:

1. ERROR when state.error is present.
2. SUCCESS when evidence exists.
3. NO_EVIDENCE otherwise.

Only modify state.status.

Do not implement the workflow orchestrator.

### Member 4 — Execution Logging

File: agent/logging_utils.py

Implement:

```python
def log_event(
    state: AgentState,
    message: str,
    level: str = "INFO"
) -> None:
    ...
```

Supported levels:
- INFO
- WARNING
- ERROR

Append formatted messages to state.logs.

Preserve the existing AgentState schema.

### Member 5 — Testing & QA

Directory: tests/

Implement unit tests for:
- Query Parser
- RAG Tool Integration
- Routing
- Logging

Coordinate integration tests with Team Leads.

Use pytest and deterministic mock fixtures.

Do not require external APIs or credentials.

## 8. Testing Requirements

All members must test their own implementation.

Run:

```bash
python -m pytest tests/ -v
```

The existing mock workflow tests cover:

1. SUCCESS
2. NO_EVIDENCE
3. ERROR

Additional module-specific unit tests
are required as modules are implemented.

A successful baseline test run does not replace
module-specific testing.

## 9. Pull Request Instructions

When implementation is ready:

1. Push or commit your changes to your branch.
2. Open the Pull Requests tab.
3. Click New pull request.
4. Set base branch to main.
5. Select your feature branch as compare.
6. Add a descriptive PR title and summary.
7. Report your testing results.
8. Request review from Team Leads.

Suggested PR title:

[Module Name] Initial Implementation

Each PR should include:

- Files changed
- Features implemented
- Tests executed and results
- Known limitations
- Dependencies or unresolved questions

Do not merge your own PR without
Team Lead approval.

## 10. Submission Timeline

### October 15 — Team Leads

- Complete Architecture and Function Contracts.
- Complete GitHub Setup.
- Verify the LangChain workflow skeleton.
- Share development instructions.

### October 19 — All Members

- Submit initial module implementation.
- Open a Pull Request.
- Share test results.
- Report blockers or interface mismatches.

### October 20 — Integration

- Team Leads review and merge modules.
- Run the first end-to-end workflow.
- Identify integration issues.

### October 21 — Testing

- Fix bugs.
- Run regression tests.
- Validate evidence and metadata.

### October 22 — Demo

Deliver a working single-agent MVP with:

- Rule-based Query Understanding
- Mock RAG Retrieval
- Conditional Routing
- Evidence with Source Metadata
- Shared State
- Execution Logs
- Passing Tests

## 11. Communication Rules

Please contact Team Leads when:

- A function contract is unclear.
- An upstream dependency is unavailable.
- A shared state change is needed.
- A module requires changes outside its ownership.
- Tests fail due to integration issues.
- Delivery timelines are at risk.

Avoid making incompatible interface changes
without notifying the team.

## 12. Definition of Done

A member's module is ready for integration when:

- The implementation follows the function contract.
- Assigned code is committed to a feature branch.
- Relevant unit tests have been run.
- A PR targeting main has been opened.
- Known limitations are documented.
- Team Leads have reviewed the PR.

Final integration acceptance is determined
by the Team Leads.

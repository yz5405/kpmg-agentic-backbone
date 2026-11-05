# Query Understanding — API & Multi-Tool Compatibility Assessment

**Owner:** Jixuan Liu (Query Understanding)
**File assessed:** `agent/query_parser.py`
**Date:** 2026-10-28
**Scope:** Check whether the current Query Parser is ready for (1) the FastAPI wrapper and (2) the upcoming Multi-Tool integration (RAG + GraphRAG + structured data).

---

## 1. TL;DR

| Area | Verdict | Summary |
|---|---|---|
| Function contract (MVP) | ✅ Pass | All four acceptance cases in `docs/function_contractsv2.md` pass. |
| API serialization | ✅ Pass | Output is plain `str`/`int`/`None`, so it survives a JSON round-trip. |
| API error semantics | ⚠️ Partial | Invalid input raises `ValueError`; the API layer still needs to map that to a 4xx vs 5xx and expose a typed response schema. |
| Multi-tool readiness | ❌ Not yet | The parser emits no question-type / intent signal and no entity/metric mentions, so a router has nothing to select RAG vs GraphRAG vs structured tools on. |
| Correctness (edge cases) | ⚠️ Fixed one | A substring false-positive bug ("metadata" → `META`, "pineapple" → `AAPL`) was found and fixed; a few gaps remain (see §4). |

**Bottom line:** the parser is correct for the single-agent MVP and can be serialized by the API today, but it is **not sufficient as a routing input** for multi-tool selection. The missing piece is a *question type / intent* signal, which this assessment and the companion roadmap document.

---

## 2. Current behavior

`understand_query(query: str) -> dict` returns exactly three keys:

```python
{"ticker": str | None, "fiscal_year": int | None, "fiscal_period": str | None}
```

- `ticker` — resolved from a hardcoded `COMPANY_TICKERS` mapping (7 companies) or a raw ticker symbol.
- `fiscal_year` — extracted only when preceded by `FY` / `fiscal year` (e.g. `FY2026`).
- `fiscal_period` — extracted from `Q1`–`Q4`.
- Raises `ValueError` on empty or non-string input.

---

## 3. Compatibility check

### 3.1 FastAPI / API integration

| Requirement | Status | Notes |
|---|---|---|
| JSON-serializable output | ✅ | Verified: `json.dumps(understand_query("Microsoft Q3 FY2026"))` round-trips to an equal dict. |
| Typed response schema | ⚠️ | `filters` is an untyped `dict`. The UI team is waiting on a real JSON response contract; a Pydantic model (e.g. `FinancialFilters`) would pin `ticker`/`fiscal_year`/`fiscal_period` and their nullability. |
| Client-vs-server error mapping | ⚠️ | `understand_query` raises `ValueError` for a bad *request* (empty query). The FastAPI layer must catch this and return **400**, while an internal parser failure should be **500**. Today both collapse into the workflow's `ERROR` status with a bare message. |
| "Couldn't understand" vs "no evidence" | ❌ | A query with all-`None` filters (e.g. `"Revenue performance"`) flows into retrieval with empty filters and usually lands on `NO_EVIDENCE`. There is no distinct **clarification** signal, which the UI team may want (e.g. prompt the user to name a company). |

### 3.2 Multi-Tool integration (RAG + GraphRAG + structured)

| Requirement | Status | Notes |
|---|---|---|
| Question-type / intent signal | ❌ | No `question_type` field. Routing RAG vs `graph_search` vs `structured_search` requires knowing *what kind* of question it is. |
| Entity mentions | ❌ | Only a single ticker is returned (first match wins). Multi-entity questions ("compare Microsoft and Apple", "who supplies NVIDIA?") are under-specified for GraphRAG relationship queries. |
| Metric mentions | ❌ | No extraction of the requested metric (`revenue`, `net income`, `EPS`, …), which structured/SQL tools need. |
| Filter schema portability | ⚠️ | `{ticker, fiscal_year, fiscal_period}` is RAG-shaped. GraphRAG's `graph_search` / `structured_search` mocks (from the GraphRAG team) will likely expect different inputs (entities, relationships, fields). |
| Ticker universe sync | ⚠️ | Hardcoded 7 companies. Must stay in sync with the ticker universe the RAG team actually retrieves (noted in a code comment), and will need to grow for GraphRAG entity coverage. |

---

## 4. Verified findings

Findings marked **[Fixed]** were corrected in this branch; the rest are documented gaps to address next.

| # | Severity | Finding | Evidence |
|---|---|---|---|
| 1 | High | **[Fixed]** Substring false-positive: `"metadata retention policy"` → `ticker=META`, `"pineapple revenue"` → `ticker=AAPL`. | Confirmed by direct run; fixed via whole-word matching in `_extract_ticker`. |
| 2 | Medium | Year without the `FY` keyword is missed: `"Tesla Q3 2026"` → `fiscal_year=None`. | Direct run. Users often write a bare year. |
| 3 | Medium | Single-entity only: the first matching company wins; no multi-entity extraction. | `_extract_ticker` returns on first match. |
| 4 | Low | `GOOG` alias not recognized — only `GOOGL`. | `KNOWN_TICKERS` contains `GOOGL` only. |
| 5 | High | No question-type / intent / metric extraction for tool selection. | `understand_query` returns only the three filter keys. |
| 6 | Medium | No clarification signal for all-`None` filters. | `"Revenue performance"` → all `None`, indistinguishable from a malformed-but-targeted query. |

Regression coverage for finding #1 is added in `tests/test_query_parser.py`.

---

## 5. Recommendations

**Already done (this week):**
- Fixed the substring false-positive (#1).
- Added `tests/test_query_parser.py` covering the four contract acceptance cases plus regression cases for the fix.

**For API readiness (coordinate with Yixuan + UI team):**
1. Add a Pydantic `FinancialFilters` (and a broader `QueryResponse`) model so the JSON contract is explicit.
2. Map `ValueError` from the parser to HTTP 400; wrap workflow-level failures as 500.
3. Decide whether to add a `needs_clarification` / `clarify` state distinct from `NO_EVIDENCE`.

**For Multi-Tool readiness (next stage — see the roadmap doc):**
4. Add a backward-compatible `classify_question()` alongside `understand_query()` that emits `question_type`, `entities`, `metric`, and a confidence flag, without changing the existing 3-key contract.
5. Sync and expand the ticker/entity universe with the RAG and GraphRAG teams.

---

## 6. Blockers / open questions for other teams

1. **GraphRAG team** — what are the exact input/output signatures of the `graph_search` and `structured_search` mock tools? This defines what the parser must emit for entity/relationship and structured questions.
2. **RAG team** — what is the actual supported ticker universe? We need it to keep `COMPANY_TICKERS` correct.
3. **UI team** — do you need a `clarify`/abstention state distinct from `NO_EVIDENCE` in the API response?

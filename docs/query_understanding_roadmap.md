# Query Understanding — Next-Stage Roadmap (Question Classification → Tool Selection)

**Owner:** Jixuan Liu (Query Understanding)
**Date:** 2026-10-28
**Status:** Proposal for team review. No production code for the classification feature has been implemented yet — this document defines the direction.

---

## 1. Goal

Extend Query Understanding from *financial-filter extraction* (what we have now) into *question classification and intent extraction*, so the workflow can decide **which retrieval tool to call** — RAG, GraphRAG, or a structured-data tool — instead of always calling RAG.

This directly prepares the `selected_tools` and multi-tool routing described in `docs/architecturev2.md` §4 / §13.

---

## 2. Why this is needed now

- The MVP parser answers *one* question: "extract company + period." It has no notion of *what the user is asking for*.
- The GraphRAG team is delivering `graph_search` and `structured_search` mock tools. Once we have more than one tool, **routing is a classification problem**: a relationship question should go to the graph, a tabulated-facts question to the structured tool, a document-evidence question to RAG.
- The classifier is the natural place to *also* emit entity and metric mentions, which GraphRAG and structured tools need as inputs.

---

## 3. Proposed question taxonomy

A first-pass taxonomy for financial Q&A, mapped to tools:

| `question_type` | Example | Target tool | Lexical signals |
|---|---|---|---|
| `metric_lookup` | "What was Microsoft's revenue in Q3 FY2026?" | RAG (document) | metric terms (`revenue`, `net income`, `EPS`, `capex`, …) + company + period |
| `relationship` | "Who are NVIDIA's major suppliers?" / "Which companies does Microsoft own?" | GraphRAG `graph_search` | relationship cues (`supplier`, `competitor`, `subsidiary`, `acquired`, `owns`, `partner`) |
| `structured_lookup` | "List Microsoft's quarterly revenue for each quarter of FY2026." | `structured_search` / SQL | tabulation cues (`list`, `each quarter`, `breakdown`, `by year`) + precise numeric |
| `comparison` | "Compare Microsoft and Apple revenue." | multi-tool fan-out + aggregation | multiple entities + `compare`, `vs`, `versus` |
| `unknown` | "Revenue performance." | clarification / abstain | no resolvable entity and no metric |

This is intentionally small and rule-friendly. It can grow once evaluation data tells us which categories actually matter.

---

## 4. Schema evolution (backward compatible)

Keep `understand_query(query) -> {ticker, fiscal_year, fiscal_period}` **unchanged** so existing tests and the RAG adapter keep working.

Add two functions beside it:

```python
def classify_question(query: str) -> dict:
    """Rule-based question classification (Phase 1)."""

def analyze_query(query: str) -> dict:
    """Combined output for the next-stage workflow."""
```

`analyze_query` is the richer, forward-compatible result:

```python
{
    # NEW — drives tool selection
    "question_type": "metric_lookup",     # or relationship / structured_lookup / comparison / unknown
    "entities": ["Microsoft"],            # multi-entity, not just one ticker
    "metric": "revenue" | None,           # metric mention, if any
    "needs_clarification": False,         # True when nothing can be resolved
    "confidence": 0.9,                    # optional, Phase 2+

    # KEPT — backward compatible with today's contract
    "ticker": "MSFT",
    "fiscal_year": 2026,
    "fiscal_period": "Q3",
}
```

This lets the next workflow read `question_type` for routing while the RAG adapter keeps reading the original three filter keys.

---

## 5. Tool-selection routing design

A routing/supervisor node (Team Leads, future) maps `question_type` to tool(s):

| `question_type` | Route to | State update |
|---|---|---|
| `metric_lookup` | RAG | `selected_tools = ["rag"]` |
| `relationship` | GraphRAG `graph_search` | `selected_tools = ["graphrag"]` |
| `structured_lookup` | `structured_search` / SQL | `selected_tools = ["structured"]` |
| `comparison` | fan-out (RAG × N or RAG + structured) then aggregate | `selected_tools = [...]` |
| `unknown` / all-`None` | clarification or abstain | short-circuit to `NO_EVIDENCE`/`clarify` |

The `selected_tools` field is already listed as a future state field in `docs/function_contractsv2.md` §13.

**Abstention:** if `needs_clarification` is `True`, the system should ask the user for a company/period rather than retrieve with empty filters. This keeps "couldn't understand" distinct from "understood but no evidence."

---

## 6. Phased plan

| Phase | Deliverable | Effort | Notes |
|---|---|---|---|
| **0 (done this week)** | Whole-word ticker fix + `tests/test_query_parser.py` + this assessment & roadmap. | Done | No contract change. |
| **1 (next sprint)** | Rule-based `classify_question()` using metric/relationship/tabulation lexicons; prototype a mock multi-tool router against the GraphRAG team's `graph_search` / `structured_search` mocks; expand the ticker/entity universe from the RAG team. | Medium | Backward compatible; rule-based only, no LLM. |
| **2** | LLM-assisted classification (few-shot) with a confidence score and fallback to the rule-based path; multi-entity extraction; handle aliases (`GOOG`/`GOOGL`). | Medium | Only after the rule-based baseline is measurable. |
| **3** | Full hierarchical multi-agent routing; evidence aggregation for `comparison`; abstention and citation validation. | Large | Matches `architecturev2.md` Stage 2. |

Phase 1 is the highest-leverage next step: it is small, needs no LLM key, and unblocks tool selection as soon as the GraphRAG mocks land.

---

## 7. Cross-team dependencies

| Team | What we need from them |
|---|---|
| GraphRAG | Exact `graph_search` / `structured_search` input/output signatures and the entity universe, to define `entities` and `question_type` mapping. |
| RAG | The real ticker/company universe, to sync `COMPANY_TICKERS` and support aliases. |
| UI | Whether the API should expose a `clarify` state distinct from `NO_EVIDENCE`. |
| Evaluation | Shared test questions to measure classification and routing accuracy. |

---

## 8. Success metrics

To be agreed with the Evaluation team; candidates already listed in `architecturev2.md` §12:

- **Filter accuracy** — ticker/year/period extraction correct on a labeled set.
- **Classification accuracy** — `question_type` matches the human label.
- **Routing accuracy** — the right tool was selected for each question.
- **Abstention precision** — `needs_clarification` fires when it should, and not when it shouldn't.

---

## 9. Open questions for the team

1. Is the five-category taxonomy enough for the first pass, or does KPMG's use case need a finer split (e.g. `risk`, `ownership`, `executive` queries)?
2. Should `comparison` be handled at the classifier level, or left to the router/aggregator?
3. Should `classify_question` stay rule-based through the next milestone, or move to an LLM classifier sooner?

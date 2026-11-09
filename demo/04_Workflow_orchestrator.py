"""Composable planning, retrieval and evidence checkpoints for SEC questions."""
from __future__ import annotations

import re
from typing import Callable, TypedDict
from uuid import uuid4
from langgraph.graph import StateGraph, START, END
from agent.query_parser import understand_query

TOOLS = ("rag", "graph_search", "structured_search")


class WorkflowState(TypedDict, total=False):
    query: str
    top_k: int
    trace_id: str
    filters: dict
    plan: dict
    evidence: list
    citations: list
    warnings: list
    logs: list
    status: str
    error: str | None
    answer: str | None
    answer_mode: str


def rule_plan(query: str) -> dict:
    """Offline baseline; ambiguous scope asks for clarification before tool calls."""
    financial = re.search(r"\b(revenue|income|profit|margin|expense|cash|assets|liabilities|filing|10-k|10-q|segment|subsidiar\w*|acquir\w*|risk|financial|fiscal|FY\d{4}|Q[1-4])\b|营收|收入|利润|财报|现金|子公司|收购|风险", query, re.I)
    if not financial:
        return {"decision": "OFF_TOPIC", "tools": [], "message": "Please ask an on-topic question about SEC filings or company financials."}
    filters = understand_query(query)
    if not filters.get("ticker"):
        return {"decision": "CLARIFY", "tools": [], "message": "Which company or ticker should I use?"}
    if not re.search(r"\b(20\d{2}|latest|recent|current)\b|最新|最近", query, re.I) and not filters.get("fiscal_year"):
        return {"decision": "CLARIFY", "tools": [], "message": "Which reporting period should I use?"}
    graph = bool(re.search(r"\b(subsidiar\w*|acquir\w*|relationship\w*|owns?|ownership|absorbed|risk factors?)\b|子公司|收购|关系", query, re.I))
    numeric = bool(re.search(r"\b(revenue|income|expense|margin|cash|how much|compare|difference)\b|收入|利润|多少|比较", query, re.I))
    tools = (["graph_search", "structured_search"] if graph and numeric else
             ["graph_search"] if graph else ["structured_search"] if numeric else ["rag"])
    # Prefer the existing RAG path until structured retrieval is explicitly enabled.
    if tools == ["structured_search"]:
        tools = ["rag"]
    return {"decision": "PROCEED", "tools": tools, "message": "Retrieve evidence for the financial question."}


def validate_plan(plan: dict) -> dict:
    if not isinstance(plan, dict) or plan.get("decision") not in {"PROCEED", "OFF_TOPIC", "CLARIFY"}:
        raise ValueError("Invalid planner decision")
    tools = plan.get("tools", [])
    if not isinstance(tools, list) or any(t not in TOOLS for t in tools) or len(set(tools)) != len(tools):
        raise ValueError("Invalid planner tools")
    if plan["decision"] == "PROCEED" and not tools:
        raise ValueError("Planner must choose a tool")
    if plan["decision"] != "PROCEED" and tools:
        raise ValueError("Blocked plans cannot call tools")
    if not isinstance(plan.get("message"), str) or not plan["message"].strip():
        raise ValueError("Planner must provide a message")
    return plan


def review_evidence(rows: list, filters: dict, trace_id: str) -> tuple[list, list]:
    """Check provenance and explicit periods, without claiming semantic correctness."""
    accepted, warnings = [], []
    for row in rows:
        meta = row.get("metadata", {})
        identity = meta.get("chunk_id") or meta.get("section_id") or meta.get("fact_id")
        valid = (row.get("text") and identity and meta.get("source_url") and
                 meta.get("accession_number") and meta.get("reporting_period_end"))
        if not valid:
            warnings.append("Evidence excluded: missing citation provenance.")
            continue
        mismatch = False
        for key in ("ticker", "fiscal_year", "fiscal_period", "reporting_period_end", "form"):
            expected = filters.get(key)
            if expected is None:
                continue
            actual = meta.get(key)
            if actual is None:
                warnings.append(f"Evidence excluded: cannot verify {key}.")
                mismatch = True
            elif str(actual).lower() not in [str(v).lower() for v in (expected if isinstance(expected, list) else [expected])]:
                warnings.append(f"Evidence excluded: {key} mismatch.")
                mismatch = True
        if mismatch:
            continue
        if meta.get("trace_id") not in (None, trace_id):
            raise ValueError("Evidence trace_id mismatch")
        accepted.append(row)
    return accepted, warnings


def build_orchestrator(tools: dict[str, Callable], planner: Callable = rule_plan,
                       generator: Callable | None = None, strategy: str = "routed"):
    if strategy not in {"routed", "combined"}:
        raise ValueError("strategy must be routed or combined")

    def plan_node(state):
        try:
            if not isinstance(state["query"], str) or not state["query"].strip():
                raise ValueError("query must be non-empty")
            if type(state["top_k"]) is not int or not 1 <= state["top_k"] <= 50:
                raise ValueError("top_k must be an integer between 1 and 50")
            plan = validate_plan(planner(state["query"]))
            filters = understand_query(state["query"])
            if plan["decision"] != "PROCEED":
                return {"plan": plan, "filters": filters, "status": plan["decision"], "answer": plan["message"]}
            if strategy == "combined":
                plan = {**plan, "tools": list(TOOLS)}
            return {"plan": plan, "filters": filters}
        except Exception as exc:
            return {"status": "ERROR", "error": str(exc)}

    def retrieve_node(state):
        rows = []
        logs = []
        try:
            for name in state["plan"]["tools"]:
                if name not in tools:
                    raise RuntimeError(f"Retrieval tool not configured: {name}")
                batch = tools[name](query=state["query"], filters=state["filters"],
                                    top_k=state["top_k"], trace_id=state["trace_id"])
                logs.append(f"[INFO] {name} completed; trace_id={state['trace_id']}")
                if not isinstance(batch, list):
                    raise ValueError("Retrieval must return a list")
                # Preserve within-tool rank; never compare raw scores across tools.
                for row in batch:
                    rows.append({**row, "metadata": {**row.get("metadata", {}), "tool": name}})
            return {"evidence": rows, "logs": logs}
        except Exception as exc:
            return {"status": "ERROR", "error": str(exc), "evidence": rows, "logs": logs}

    def review_node(state):
        try:
            rows, warnings = review_evidence(state["evidence"], state["filters"], state["trace_id"])
            citations = [{"id": f"E{i}", **r["metadata"]} for i, r in enumerate(rows, 1)]
            return {"evidence": rows, "warnings": warnings, "citations": citations,
                    "status": "SUCCESS" if rows else "NO_EVIDENCE"}
        except Exception as exc:
            return {"status": "ERROR", "error": str(exc)}

    def answer_node(state):
        if state["status"] == "NO_EVIDENCE":
            return {"answer": "I could not find sufficiently verifiable evidence for this question."}
        try:
            if generator is None:
                # Explicit evidence-only fallback, never advertised as a synthesized answer.
                answer = "Evidence excerpts (not a generated financial answer):\n" + "\n".join(
                    f"[E{i}] {r['text']}" for i, r in enumerate(state["evidence"], 1))
                return {"answer": answer, "answer_mode": "extractive"}
            generated = generator(state["query"], state["evidence"])
            if isinstance(generated, dict):
                decision = generated.get("decision")
                if decision not in {"ANSWER", "ABSTAIN", "CLARIFY"}:
                    raise ValueError("Invalid evidence review decision")
                if decision != "ANSWER":
                    message = generated.get("answer")
                    if not isinstance(message, str) or not message.strip():
                        raise ValueError("Missing checkpoint explanation")
                    return {"status": "NO_EVIDENCE" if decision == "ABSTAIN" else "CLARIFY",
                            "answer": message, "answer_mode": "generated"}
                answer = generated.get("answer")
            else:
                answer = generated
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Empty generated answer")
            refs = re.findall(r"\[E(\d+)\]", answer)
            if not refs or any(not 1 <= int(r) <= len(state["evidence"]) for r in refs):
                raise ValueError("Answer must cite valid evidence IDs")
            return {"answer": answer, "answer_mode": "generated"}
        except Exception as exc:
            return {"status": "ERROR", "error": str(exc), "answer": None}

    graph = StateGraph(WorkflowState)
    for name, node in (("plan", plan_node), ("retrieve", retrieve_node), ("review", review_node), ("answer", answer_node)):
        graph.add_node(name, node)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", lambda s: "retrieve" if s["status"] == "PENDING" else END)
    graph.add_conditional_edges("retrieve", lambda s: END if s["status"] == "ERROR" else "review")
    graph.add_conditional_edges("review", lambda s: END if s["status"] == "ERROR" else "answer")
    graph.add_edge("answer", END)
    return graph.compile()


def run_orchestrator(query, top_k=8, *, tools, planner=rule_plan, generator=None, strategy="routed", trace_id=None):
    return build_orchestrator(tools, planner, generator, strategy).invoke({
        "query": query, "top_k": top_k, "trace_id": trace_id or str(uuid4()),
        "filters": {}, "plan": {}, "evidence": [], "citations": [], "warnings": [],
        "logs": [], "status": "PENDING", "error": None, "answer": None, "answer_mode": "none",
    })


"""Coverage-scoped RAG retrieval for the joint integration."""

import re
from time import perf_counter

from agent.tool_selection import _has_sec_provenance, describe_retrieval_error, select_tool
from agent.tools.rag_tool import _to_evidence

_POSSESSIVE = re.compile(r"\b([A-Z][\w-]+)[’']s\b")
_LATEST_QUARTER = re.compile(r"\b(?:latest|last|most recent)\s+(?:fiscal\s+)?quarter\b", re.I)
_YOY = re.compile(r"\b(year over year|year-over-year|yoy|by what percentage)\b", re.I)
_EXHIBIT = re.compile(r"\bexhibit\s+21\b", re.I)


def coverage_plan(state):
    from rag.coverage import check_coverage, default_index, extract_request

    question = state["query"]
    request = extract_request(question)
    rule_companies = request.pop("companies") or []
    parsed = state["filters"].get("ticker") or []
    parsed = [parsed] if isinstance(parsed, str) else list(parsed)
    # Keep the Agent's company ordering and supplement a dropped or misspelled mention.
    companies = list(dict.fromkeys([*parsed, *rule_companies]))
    if not companies:
        companies = [state["company"]] if state.get("company") else _POSSESSIVE.findall(question)
    latest = not any(request.values()) and bool(_LATEST_QUARTER.search(question))
    if latest:
        request["forms"] = ["10-Q"]
    coverage = check_coverage(companies=companies, **request)
    filters = {}
    subqueries = []
    if coverage["status"] in {"all_hit", "partial"}:
        hits = {}
        for target in coverage["targets"]:
            if target["status"] == "hit":
                hits.setdefault(target["ticker"], set()).update(target["accessions"])
        if latest:
            index = default_index()
            for ticker, accessions in hits.items():
                filing = max(
                    (f for f in index.by_ticker[ticker] if f.accession in accessions),
                    key=lambda f: (f.period_end is not None, f.period_end, f.accession),
                )
                hits[ticker] = {filing.accession}
        filters = {"ticker": list(hits), "accession_number": sorted(set().union(*hits.values()))}
        subqueries = [{
            "query": question, "label": f"ticker={ticker}",
            "filters": {"ticker": ticker, "accession_number": sorted(accessions)},
        } for ticker, accessions in hits.items()]
    return {
        "status": coverage["status"], "targets": coverage["targets"],
        "entities": coverage["entities"], "message": coverage["message"],
        "companies": companies, "periods": request, "filters": filters,
    }, subqueries


def run_joint_retrieval(state, trace_id, graph_enabled):
    started = perf_counter()
    result = {
        "status": "NO_EVIDENCE", "evidence": [], "retrieval_attempts": [],
        "joint_trace": {"retrieval_called": False, "n_subqueries": 0, "latency_ms": {},
                        "returned_count": 0, "accepted_count": 0, "candidate_citations": []},
    }
    trace = result["joint_trace"]
    try:
        precheck, subqueries = coverage_plan(state)
        trace["precheck"] = precheck
        trace["latency_ms"]["precheck"] = round((perf_counter() - started) * 1000, 2)
        result["filters"] = precheck["filters"]
        if precheck["status"] in {"none", "unresolved"}:
            return {**result, "answer": precheck["message"], "selected_tool": "direct_reply"}
        if precheck["status"] == "no_target":
            _, intent = select_tool(state["query"], state["question_type"], {})
            if intent == "unsupported_calculation":
                return {
                    **result, "selected_tool": "direct_reply",
                    "answer": "There is insufficient evidence for a verified cross-company calculation.",
                }
            return {**result, "answer": "Which company should I look up?", "selected_tool": "clarification"}
        if _EXHIBIT.search(state["query"]):
            return {
                **result, "selected_tool": "graph" if graph_enabled else None,
                "retrieval_limitation": "The frozen RAG index excludes exhibits and Graph Search does not count Exhibit 21 subsidiaries.",
            }
        result["selected_tool"] = "vector"
        trace["retrieval_called"] = True
        started = perf_counter()
        from rag.retrieve import retrieve_multi

        envelope = retrieve_multi(
            state["query"], filters=precheck["filters"], subqueries=subqueries, top_k=state["top_k"],
            trace_id=trace_id,
        )
        trace["latency_ms"]["retrieval"] = round((perf_counter() - started) * 1000, 2)
        trace["n_subqueries"] = len(envelope["subqueries"]) + len(envelope["skipped"])
        trace["subqueries"] = envelope["subqueries"] + envelope["skipped"]
        started = perf_counter()
        rows = [_to_evidence(row) for row in envelope["results"]]
        scoped = {(sq["filters"]["ticker"], a) for sq in subqueries for a in sq["filters"]["accession_number"]}
        accepted = [
            row for row in rows if _has_sec_provenance(row)
            and (row["metadata"]["ticker"], row["metadata"].get("accession_number")) in scoped
            and row["metadata"].get("chunk_id") and row.get("text", "").strip()
        ]
        trace["returned_count"] = len(rows)
        trace["candidate_citations"] = [
            {k: row["metadata"].get(k) for k in ("ticker", "accession_number", "chunk_id")}
            for row in rows
        ]
        # A relationship label can describe an ordinary SEC disclosure, such as
        # the segment that includes a product. Only explicit traversal wording
        # should suppress otherwise eligible RAG evidence.
        question_type = state["question_type"]
        _, intent = select_tool(
            state["query"], None if question_type == "relationship" else question_type, precheck["filters"],
        )
        # Keep both sides in the trace while withholding unsupported calculations from the answer model.
        comparison = len(subqueries) > 1 and bool(re.search(r"\b(compare|comparison|versus)\b", state["query"], re.I))
        if intent.startswith("unsupported_") or comparison or _YOY.search(state["query"]):
            accepted = []
            result["retrieval_limitation"] = (
                "A deterministic calculator or supported graph operation is required for this question."
            )
        trace["accepted_count"] = len(accepted)
        trace["latency_ms"]["evidence_validation"] = round((perf_counter() - started) * 1000, 2)
        return {
            **result, "evidence": accepted, "evidence_status": envelope["evidence_status"],
            "weak_reasons": envelope["weak_reasons"], "used_tool": "vector",
            "status": "SUCCESS" if accepted else "NO_EVIDENCE",
            "retrieval_attempts": [{"tool": "vector", "outcome": "accepted" if accepted else "insufficient_evidence",
                                    "returned_count": len(rows), "accepted_count": len(accepted)}],
        }
    except Exception as exc:
        failure = describe_retrieval_error(exc)
        return {**result, "status": "ERROR", "error": failure["reason"], "retrieval_failure": failure}

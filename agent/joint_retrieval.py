"""Coverage-scoped RAG retrieval for the joint integration."""

import re
from time import perf_counter

from agent.joint_evidence import financial_inputs, is_quarter_cloud_drivers, quarter_cloud_evidence
from agent.tool_selection import _has_sec_provenance, describe_retrieval_error, is_subsidiary_lookup, needs_fiscal_year, run_tool_selection, select_tool
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


def _graph_filters(state, precheck):
    periods = precheck["periods"]
    tickers = list(dict.fromkeys(e["ticker"] for e in precheck["entities"] if e.get("ticker")))
    if not tickers:
        parsed = state["filters"].get("ticker")
        tickers = [parsed] if isinstance(parsed, str) else (parsed or [])
    filters = {"ticker": tickers[0] if len(tickers) == 1 else tickers} if tickers else {}
    for source, destination in (
        ("fiscal_years", "fiscal_year"), ("fiscal_periods", "fiscal_period"),
        ("forms", "form"), ("period_ends", "reporting_period_end"),
    ):
        values = periods.get(source) or []
        if len(values) == 1:
            filters[destination] = values[0]
    return filters


def run_joint_retrieval(state, trace_id, graph_enabled, tools=None):
    started = perf_counter()
    result = {
        "status": "NO_EVIDENCE", "evidence": [], "retrieval_attempts": [],
        "joint_trace": {"retrieval_called": False, "n_subqueries": 0, "latency_ms": {},
                        "returned_count": 0, "accepted_count": 0, "candidate_citations": []},
    }
    trace = result["joint_trace"]
    primary_attempt = None
    try:
        precheck, subqueries = coverage_plan(state)
        trace["precheck"] = precheck
        trace["latency_ms"]["precheck"] = round((perf_counter() - started) * 1000, 2)
        result["filters"] = precheck["filters"]
        graph_filters = _graph_filters(state, precheck)
        graph_state = {**state, "filters": graph_filters, "form": None, "logs": state.get("logs", [])}
        primary, intent = select_tool(
            state["query"], None if state["question_type"] == "relationship" else state["question_type"], graph_filters,
        )
        if needs_fiscal_year(graph_filters):
            return {**result, "selected_tool": "clarification",
                    "answer": "Which fiscal year should I use for that quarter?"}
        if intent == "unsupported_relationship":
            return {**result, "retrieval_limitation": "Graph Search supports claim lookup, not relationship traversal."}
        if (tools and primary in {"graph", "structured"} and primary in tools and graph_filters.get("ticker")
                and not _EXHIBIT.search(state["query"]) and not _YOY.search(state["query"])
                and not is_quarter_cloud_drivers(state["query"])):
            primary_attempt = run_tool_selection(
                graph_state, {primary: tools[primary]}, trace_id, route=(primary, intent),
            )
            attempt = primary_attempt["retrieval_attempts"][0]
            trace["backend_attempts"] = primary_attempt["retrieval_attempts"]
            trace["returned_count"] = attempt.get("returned_count", 0)
            trace["accepted_count"] = attempt.get("accepted_count", 0)
            if (primary_attempt["status"] == "SUCCESS" or not subqueries or is_subsidiary_lookup(state["query"])
                    or attempt.get("failure", {}).get("type") in {"invalid_request", "unsupported_filter"}):
                return {**result, **primary_attempt}
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
        comparison = len(subqueries) > 1 and bool(re.search(r"\b(compare|comparison|versus)\b", state["query"], re.I))
        periods = precheck["periods"].get("period_ends") or []
        if intent == "unsupported_calculation" or comparison or _YOY.search(state["query"]):
            accepted = financial_inputs(accepted, state["query"], periods)
            result["calculation_status"] = "blocked"
            result["calculation_reason"] = "unsupported_calculation"
            result["retrieval_limitation"] = "A deterministic calculator is required for this question."
        elif intent == "unsupported_relationship":
            accepted = []
            result["retrieval_limitation"] = "A supported graph operation is required for this question."
        elif is_quarter_cloud_drivers(state["query"]):
            accepted = quarter_cloud_evidence(accepted, periods)
        trace["calculation_status"] = result.get("calculation_status", "not_required")
        trace["calculation_reason"] = result.get("calculation_reason")
        if (tools and not primary_attempt and "graph" in tools and intent == "narrative"
                and graph_filters.get("ticker")
                and re.search(r"\b(?:competiti\w*|disclosure\w*|risk\w*)\b", state["query"], re.I)
                and not is_quarter_cloud_drivers(state["query"])
                and (not accepted or envelope["evidence_status"] in {"weak", "empty"})):
            alternate = run_tool_selection(graph_state, {"graph": tools["graph"]}, trace_id, route=("graph", "narrative"))
            vector_attempt = {"tool": "vector", "outcome": "insufficient_evidence",
                              "returned_count": len(rows), "accepted_count": 0,
                              "evidence_status": envelope["evidence_status"],
                              "latency_ms": trace["latency_ms"]["retrieval"]}
            alternate["retrieval_attempts"].insert(0, vector_attempt)
            trace["backend_attempts"] = alternate["retrieval_attempts"]
            trace["accepted_count"] = len(alternate["evidence"])
            return {**result, **alternate, "selected_tool": "vector", "should_try_graphrag": True,
                    "weak_reasons": envelope["weak_reasons"]}
        trace["accepted_count"] = len(accepted)
        trace["latency_ms"]["evidence_validation"] = round((perf_counter() - started) * 1000, 2)
        return {
            **result, "selected_tool": primary_attempt["selected_tool"] if primary_attempt else "vector",
            "retrieval_failure": primary_attempt.get("retrieval_failure") if primary_attempt else None,
            "should_try_graphrag": bool(primary_attempt), "evidence": accepted, "evidence_status": envelope["evidence_status"],
            "weak_reasons": envelope["weak_reasons"], "used_tool": "vector",
            "status": "SUCCESS" if accepted else "ERROR" if primary_attempt and primary_attempt["status"] == "ERROR" else "NO_EVIDENCE",
            "error": primary_attempt.get("error") if primary_attempt and not accepted else None,
            "retrieval_attempts": (primary_attempt["retrieval_attempts"] if primary_attempt else []) + [{
                "tool": "vector", "outcome": "accepted" if accepted else "insufficient_evidence",
                "returned_count": len(rows), "accepted_count": len(accepted),
                "latency_ms": trace["latency_ms"]["retrieval"], "evidence_status": envelope["evidence_status"],
            }],
        }
    except Exception as exc:
        failure = describe_retrieval_error(exc)
        return {**result, "status": "ERROR", "error": failure["reason"], "retrieval_failure": failure}

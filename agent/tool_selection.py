"""Capability-aware retrieval policy with one alternate backend attempt."""

import re
from time import perf_counter
from urllib.parse import urlsplit

from agent.routing import evaluate_financial_evidence, evaluate_structured_lookup

_RANKING = re.compile(r"\b(rank|highest|lowest|fastest|net margin|growth rate)\b", re.I)
_ARITHMETIC = re.compile(r"\b(calculate|compute|add up|sum of|percentage change)\b", re.I)
_NUMERIC = re.compile(r"\b(revenue|income|margin|cash flow|earnings|percent|ratio)\b", re.I)
_GRAPH_CLAIMS = re.compile(r"\b(claims?|disclosures?)\b.*\b(about|mentioning|on)\b", re.I)
_SUBSIDIARY = re.compile(r"\b(subsidiar(?:y|ies)|owns|acquired)\b", re.I)
_TRAVERSAL = re.compile(r"\b(shared|both|connect|relationship|related|path|traverse|across|compare)\b", re.I)


def select_tool(query, question_type, filters):
    """Return the primary tool and the evidence requirements for the question."""
    if _RANKING.search(query) or _ARITHMETIC.search(query) or (
        _NUMERIC.search(query) and (
            question_type == "comparison"
            or re.search(r"\b(compare|versus|vs\.?|difference between|combined)\b", query, re.I)
            or re.search(r"\b(?:which company|who)\b.*\b(?:more|less|higher|lower|greater)\b", query, re.I)
        )
    ):
        return "vector", "unsupported_calculation"
    if question_type in {"metric_lookup", "structured_lookup"} or (
        _NUMERIC.search(query) and re.match(r"(?:what (?:was|is)|how much)\b", query, re.I)
    ):
        if isinstance(filters.get("ticker"), str) and (filters.get("fiscal_year") or filters.get("reporting_period_end")):
            return "structured", "financial"
        return "vector", "financial"
    if (_GRAPH_CLAIMS.search(query) or _SUBSIDIARY.search(query)) and not _TRAVERSAL.search(query):
        return "graph", "narrative"
    if question_type == "relationship" or (
        _TRAVERSAL.search(query) and re.search(r"\b(relationship|connect|path|traverse|shared|related)\b", query, re.I)
    ):
        return "vector", "unsupported_relationship"
    return "vector", "narrative"


def describe_retrieval_error(exc):
    """Expose an actionable category without serializing driver connection details."""
    kinds = {
        "FilterNotSupportedError": ("unsupported_filter", "The tool does not support the requested filters."),
        "RetrievalUnavailableError": ("backend_unavailable", "The retrieval backend is unavailable."),
        "QueryGenerationError": ("query_generation_failure", "The backend could not generate a supported query."),
    }
    if type(exc).__name__ in kinds:
        code, reason = kinds[type(exc).__name__]
    elif isinstance(exc, ValueError):
        code, reason = "invalid_request", "The retrieval request is invalid."
    elif isinstance(exc, (ConnectionError, TimeoutError, OSError, ImportError)):
        code, reason = "backend_unavailable", "The retrieval backend is unavailable."
    else:
        code, reason = "backend_failure", "The retrieval backend failed."
    return {"type": code, "reason": reason}


def _has_sec_provenance(evidence):
    metadata = evidence.get("metadata", {})
    try:
        url = urlsplit(metadata.get("source_url") or "")
    except ValueError:
        return False
    accession = metadata.get("accession_number")
    filing_path = re.match(r"^/Archives/edgar/data/(\d+)/(\d{18})/", url.path)
    return bool(
        url.scheme == "https" and url.netloc.lower() in {"sec.gov", "www.sec.gov"}
        and filing_path and (not accession or str(accession).replace("-", "") == filing_path[2])
        and metadata.get("ticker") and metadata.get("form")
        and any(metadata.get(key) for key in ("section_id", "fact_id", "chunk_id"))
    )


def _matches_filters(item, filters, tool):
    metadata = item["metadata"]
    for key in ("ticker", "form", "fiscal_year", "fiscal_period", "reporting_period_end"):
        expected = filters.get(key)
        actual = metadata.get(key)
        if expected is None:
            continue
        # GraphRAG enforces fiscal filters against filing dates without echoing
        # fiscal labels. Skip this redundant check only for absent fiscal labels.
        if actual is None and key.startswith("fiscal_") and tool in {"graph", "structured"}:
            continue
        if actual not in (expected if isinstance(expected, list) else [expected]):
            return False
    return True


def is_subsidiary_lookup(query):
    return bool(_SUBSIDIARY.search(query))


def _subsidiary_claim_matches(query, evidence):
    location = re.search(r"\bin ([A-Z][A-Za-z-]+(?: [A-Z][A-Za-z-]+)*)[?.]?\s*$", query)
    return bool(_SUBSIDIARY.search(evidence["text"]) and (
        not location or re.search(rf"\b{re.escape(location[1])}\b", evidence["text"], re.I)
    ))


def needs_fiscal_year(filters):
    return bool(filters.get("fiscal_period") and not (
        filters.get("fiscal_year") or filters.get("reporting_period_end")
    ))


def run_tool_selection(state, tools, trace_id, *, route=None):
    filters = dict(state["filters"])
    if state["form"]:
        filters["form"] = state["form"]
    if needs_fiscal_year(filters):
        return {
            "status": "NO_EVIDENCE", "selected_tool": "clarification", "retrieval_attempts": [],
            "answer": "Which fiscal year should I use for that quarter?", "filters": filters,
            "logs": state["logs"],
        }
    primary, intent = route or select_tool(state["query"], state["question_type"], filters)
    if filters.get("reporting_period_end") and not filters.get("fiscal_year"):
        filters.pop("fiscal_period", None)
    alternative = {"structured": "vector", "graph": "vector"}.get(primary)
    if primary == "graph" and is_subsidiary_lookup(state["query"]):
        alternative = None
    if primary == "vector" and intent == "financial" and filters.get("fiscal_year"):
        alternative = "structured"

    attempts, logs, accepted = [], [], []
    for tool in dict.fromkeys((primary, alternative)):
        if tool not in tools:
            continue
        start = perf_counter()
        retry_count = 0
        request = {"query": state["query"], "filters": filters, "top_k": state["top_k"], "trace_id": trace_id}
        try:
            try:
                result = tools[tool](**request)
            except Exception as exc:
                if tool != "graph" or type(exc).__name__ != "RetrievalUnavailableError":
                    raise
                retry_count = 1
                result = tools[tool](**request)
            rows = result["evidence"] if isinstance(result, dict) else result
            signal = result.get("evidence_status") if isinstance(result, dict) else None
            matched = [row for row in rows if _has_sec_provenance(row) and _matches_filters(row, filters, tool)]
            if tool == "graph" and is_subsidiary_lookup(state["query"]):
                matched = [row for row in matched if _subsidiary_claim_matches(state["query"], row)]
            if intent == "financial" and tool == "structured":
                accepted = evaluate_structured_lookup(state["query"], matched, filters)
            elif intent == "financial":
                accepted = evaluate_financial_evidence(
                    query=state["query"], rag_evidence=matched if tool == "vector" else [],
                    graphrag_evidence=matched if tool != "vector" else [],
                    evidence_status=signal, weak_reasons=[],
                )
            elif intent == "narrative" and signal != "weak":
                accepted = matched
            outcome = "accepted" if accepted else "insufficient_evidence" if rows else "no_match"
            attempt = {
                "tool": tool, "outcome": outcome, "evidence_status": signal,
                "returned_count": len(rows), "accepted_count": len(accepted),
            }
        except Exception as exc:
            attempt = {"tool": tool, "outcome": "failed", "failure": describe_retrieval_error(exc)}
        attempt["retry_count"] = retry_count
        attempt["latency_ms"] = round((perf_counter() - start) * 1000, 2)
        attempts.append(attempt)
        detail = attempt.get("failure", {}).get("type", attempt["outcome"])
        logs.append(f"[INFO] Retrieval {tool}: {detail}")
        error = attempt.get("failure")
        if accepted or (error and error["type"] in {"invalid_request", "unsupported_filter"}):
            break

    failure = next((item["failure"] for item in attempts if "failure" in item), None)
    limitation = {
        "unsupported_calculation": "This comparison or ranking requires verified coverage and deterministic computation.",
        "unsupported_relationship": "The graph tool supports claim lookup, not relationship traversal.",
    }.get(intent)
    return {
        "selected_tool": primary,
        "retrieval_attempts": attempts,
        "retrieval_failure": failure,
        "retrieval_limitation": limitation,
        "should_try_graphrag": len(attempts) > 1,
        "used_tool": attempts[-1]["tool"] if accepted else None,
        "evidence": accepted,
        "evidence_status": attempts[-1].get("evidence_status") if attempts else None,
        "status": "SUCCESS" if accepted else "ERROR" if failure else "NO_EVIDENCE",
        "error": failure["reason"] if failure and not accepted else None,
        "logs": state["logs"] + logs,
    }

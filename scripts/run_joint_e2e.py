"""Run the supplied 15-case joint checklist against real local Chroma."""
import argparse
import collections
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from fastapi.testclient import TestClient

from api.main import app


def checklist(path):
    rows = []
    for line in path.read_text().splitlines():
        match = re.match(r"\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|$", line)
        if match:
            number, question, expected = match.groups()
            rows.append({"case": int(number), "checklist_question": question, "question": question, "expected": expected})
    if [r["case"] for r in rows] != list(range(1, 16)):
        raise ValueError("Expected the supplied checklist with cases 1–15")
    rows[1]["question"] = rows[0]["question"].replace("Microsoft", "Microsfot")
    rows[13]["question"] = rows[0]["question"]
    rows[14]["question"] = rows[7]["question"]
    return rows


def execute(case, question, graph):
    os.environ["KPMG_GRAPHRAG_ENABLED"] = "1" if graph else "0"
    trace_id = f"joint-e2e-{case:02d}"
    with TestClient(app) as client:
        response = client.post("/query", json={"query": question, "top_k": 15, "trace_id": trace_id})
    return {**response.json(), "runner_pid": os.getpid()}


def verdict(case, response, joint, compare_equal):
    pre = joint.get("precheck") or {}
    state = pre.get("status")
    called = joint.get("retrieval_called", False)
    targets = {t.get("ticker") for t in pre.get("targets", []) if t.get("status") == "hit"}
    answer = response.get("answer") or ""
    accepted = joint.get("accepted_count", 0)
    if response.get("status") == "ERROR" or "detail" in response:
        return "BLOCKED", response.get("error") or response.get("detail")
    if case in (6, 7):
        expected = "unresolved" if case == 6 else "none"
        ok = state == expected and not called and bool(answer)
        return ("PASS", f"{state}; direct reply with no retrieval") if ok else ("FAIL", f"Expected {expected} and no retrieval; got {state}")
    if case == 10:
        ok = state == "no_target" and not called and response.get("selected_tool") == "clarification"
        return ("PASS", "Asked for a company without retrieval") if ok else ("FAIL", "Clarification contract failed")
    if case == 11:
        ok = response.get("status") == "NO_EVIDENCE" and "insufficient evidence" in answer.lower()
        return ("PASS", "Explicitly abstained from unsupported ranking") if ok else ("FAIL", "Ranking was not safely declined")
    if case == 13:
        selected = response.get("selected_tool")
        return ("BLOCKED", "Graph selected; upstream lexical claims search cannot count Exhibit 21 subsidiaries") if selected == "graph" else ("FAIL", "Graph intent was not recognized")
    if case == 14:
        if compare_equal is False:
            return "FAIL", "Fresh process returned a different ordered sequence of evidence IDs"
        if compare_equal is True:
            return "PASS", "Fresh process returned identical ordered evidence IDs"
        return "BLOCKED", "Evidence IDs were unavailable for the fresh-process comparison"
    if case == 4:
        seen = {c["ticker"] for c in joint.get("candidate_citations", [])}
        if targets != {"MSFT", "AAPL"} or joint.get("n_subqueries") != 2 or seen != targets:
            return "FAIL", f"Expected two scoped subqueries with both companies; observed {sorted(seen)}"
        return "BLOCKED", "Two real subqueries returned both tickers; deterministic comparison calculator is unavailable"
    if case == 5:
        return ("PASS", "Mircon resolved to MU and real retrieval ran") if targets == {"MU"} and called else ("FAIL", "MU typo resolution or retrieval failed")
    if case == 12:
        return ("BLOCKED", "Real filing retrieval ran; deterministic YoY calculator is unavailable") if called else ("FAIL", "Expected real retrieval before calculation")
    if case in (1, 2, 3, 8, 9, 15):
        if pre.get("status") != "all_hit" or not called or not accepted:
            return "FAIL", "Expected covered retrieval and accepted SEC evidence"
        if case in (1, 2, 3, 8, 15) and pre["filters"]["accession_number"] != ["0001193125-26-191507"]:
            return "FAIL", "Retrieval was not scoped to the expected March 2026 filing"
        if not answer or not response.get("llm_calls"):
            return "BLOCKED", f"Accepted {accepted} real evidence rows; approved LLM answer unavailable"
        required = {1: "82886", 2: "82886", 3: "31778", 9: "productivity and business processes"}.get(case)
        if required and required not in answer.lower().replace(",", ""):
            return "FAIL", "Generated answer did not contain the checklist result"
        citations = response.get("citations", [])
        if not citations or any(not c.get("accession_number") or not c.get("chunk_id") for c in citations):
            return "FAIL", "Generated answer did not include accession and chunk citations"
        if case in (8, 15) and not any(
            "management" in str(c.get("section_title", "")).lower() or "md&a" in str(c.get("section", "")).lower()
            for c in citations
        ):
            return "FAIL", "Generated answer did not cite MD&A"
        return "PASS", "Checklist answer and cited evidence observed"
    raise ValueError(case)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("checklist", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fresh", action="store_true")
    args = parser.parse_args()
    cases = checklist(args.checklist)
    if args.fresh:
        response = execute(14, cases[13]["question"], False)
        print(json.dumps(response))
        return
    index = Path(os.environ["RAG_CHROMA_DIR"])
    meta = json.loads((index / "meta.json").read_text())
    if meta.get("index_version") != "7a7ad9801f86" or os.getenv("RAG_BACKEND") != "chroma":
        parser.error("The checklist requires frozen Chroma index 7a7ad9801f86")
    from rag.chroma_backend import persistence_report

    persistence = persistence_report(index)
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    citation_review = None
    for item in cases:
        number = item["case"]
        if number == 14:
            response = json.loads(subprocess.check_output([
                sys.executable, __file__, str(args.checklist), str(args.output), "--fresh",
            ], text=True))
        else:
            response = execute(number, item["question"], number in (13, 15))
        joint = response.get("joint_trace") or {}
        pre = joint.get("precheck") or {}
        candidates = joint.get("candidate_citations", [])
        evidence = response.get("evidence", [])
        ordered_ids = [item["metadata"].get("chunk_id") for item in evidence]
        compare_equal = None
        if number == 14 and ordered_ids and records[0]["ordered_evidence_ids"]:
            compare_equal = (
                response["runner_pid"] != records[0]["runner_pid"]
                and candidates == records[0]["candidate_citations"]
                and ordered_ids == records[0]["ordered_evidence_ids"]
            )
        if number == 8:
            citation_review = {
                "question": item["question"], "trace_id": response.get("trace_id"),
                "index_version": meta["index_version"], "backend": "chroma",
                "answer_status": "Model Answer Returned" if response.get("answer") and response.get("llm_calls")
                                 else "Final Answer Pending Authorization",
                "answer": response.get("answer"),
                "retrieval_citations": response.get("citations", []),
                "evidence": [
                    {**{key: row["metadata"].get(key) for key in
                         ("chunk_id", "accession_number", "section", "section_title", "source_url")},
                     "text": row["text"]}
                    for row in evidence
                ],
            }
        outcome, reason = verdict(number, response, joint, compare_equal)
        records.append({
            **item, "trace_id": response.get("trace_id"), "index_version": meta["index_version"],
            "backend": "chroma", "hnsw_persisted_meta": meta.get("hnsw_persisted"),
            "hnsw_runtime_inspection": persistence, "graph_enabled": number in (13, 15),
            "query_understanding_mode": response.get("query_understanding_mode"),
            "parsed_companies": pre.get("companies"), "parsed_periods": pre.get("periods"),
            "precheck": pre, "retrieval_called": joint.get("retrieval_called", False),
            "n_subqueries": joint.get("n_subqueries", 0), "subqueries": joint.get("subqueries", []),
            "evidence_status": response.get("evidence_status"), "weak_reasons": response.get("weak_reasons", []),
            "returned_count": joint.get("returned_count", 0), "accepted_count": joint.get("accepted_count", 0),
            "selected_tool": response.get("selected_tool"), "used_tool": response.get("used_tool"),
            "fallback_attempts": response.get("fallback_attempts"), "answer": response.get("answer"),
            "citations": response.get("citations", []), "candidate_citations": candidates,
            "ordered_evidence_ids": ordered_ids, "runner_pid": response["runner_pid"],
            "fresh_process_order_match": compare_equal,
            "latency_ms": {**joint.get("latency_ms", {}), "query_understanding": response.get("query_understanding_ms"),
                           "answer": response.get("answer_ms"), "total": response.get("latency_ms")},
            "outcome": outcome, "reason": reason,
        })
        print(number, outcome, reason, flush=True)
    counts = collections.Counter(row["outcome"] for row in records)
    (args.output / "joint-e2e-15-traces.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records))
    if citation_review is not None:
        (args.output / "case-08-citation-review.json").write_text(
            json.dumps(citation_review, ensure_ascii=False, indent=2) + "\n",
        )
    report = [
        "# Agent × RAG joint E2E", "",
        f"PASS {counts['PASS']} · FAIL {counts['FAIL']} · BLOCKED {counts['BLOCKED']}", "",
        f"Frozen Chroma {meta['index_version']}. Metadata hnsw_persisted: {meta.get('hnsw_persisted')!r}. "
        f"Upstream read-only persistence report: {persistence}.",
        "Outcomes are per case. Formal frozen-index sign-off additionally requires the expected persistence flag and verified persisted graph.",
        "", "| Case | Outcome | Reason |", "| --- | --- | --- |",
    ]
    report += [f"| {r['case']} | {r['outcome']} | {r['reason']} |" for r in records]
    (args.output / "joint-e2e-15-results.md").write_text("\n".join(report) + "\n")


if __name__ == "__main__":
    main()

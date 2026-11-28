"""Run local real-backend GraphRAG acceptance probes without calling an LLM."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient

from api.main import app

CASES = (
    ("quarter_revenue", "What was Microsoft's total revenue for the three months ended March 31, 2026?", "structured"),
    ("quarter_net_income", "What was Microsoft's net income in Q3 FY2026?", "structured"),
    ("apple_period", "What was Apple's revenue in Q3 FY2026?", "structured"),
    ("claims", "Find Microsoft claims about competition", "graph"),
    ("subsidiary_claims", "Which subsidiaries does Apple have in Ireland?", "graph"),
    ("narrative", "What drove the growth in Microsoft's Intelligent Cloud revenue in the quarter ended March 31, 2026?", "vector"),
    ("vector_structured", "What was Microsoft's revenue in FY2026?", "vector→structured"),
    ("vector_graph", "What risks does Microsoft identify from competition for AI research talent in Europe?", "vector→graph"),
    ("traversal", "Find a relationship path connecting Microsoft's and Apple's subsidiaries.", "unsupported traversal"),
    ("quarter_clarify", "What was Nike's revenue in Q3?", "clarification"),
    ("coverage_miss", "What was Tesla's revenue in 2025?", "unresolved, no retrieval"),
    ("unavailable", "Find Microsoft claims about competition", "backend_unavailable"),
)

PROVENANCE = ("trace_id", "ticker", "form", "accession_number", "section_id", "fact_id", "claim_id",
              "retrieval_method", "source_url", "reporting_period_end", "period_start", "period_end")


@contextmanager
def options(case):
    updates = {"KPMG_TOOL_SELECTION": "legacy" if case == "vector_structured" else "auto",
               "KPMG_COVERAGE_PRECHECK": "0" if case in {"vector_structured", "unavailable"} else "1"}
    previous = {key: os.environ.get(key) for key in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def request(client, case, question):
    with options(case):
        response = client.post("/query", json={"query": question, "top_k": 15, "trace_id": f"joint-graph-{case}"})
    response.raise_for_status()
    return response.json()


def verdict(case, expected, data):
    if case in {"quarter_revenue", "quarter_net_income", "apple_period", "claims", "subsidiary_claims", "narrative"}:
        if data["status"] == "ERROR":
            return "BLOCKED", str(data.get("retrieval_failure"))
        if not data["evidence"]:
            return "BLOCKED", "Real backend returned no eligible scoped evidence"
        if data["used_tool"] != expected:
            return "FAIL", "Unexpected accepted backend"
        if expected in {"graph", "structured"}:
            ids = ("claim_id", "section_id") if expected == "graph" else ("fact_id",)
            method = "neo4j_fulltext_claim" if expected == "graph" else "duckdb_concept_match"
            if not all(
                e["metadata"].get("retrieval_method") == method
                and e["metadata"].get("trace_id") == data["trace_id"]
                and e["metadata"].get("accession_number")
                and all(e["metadata"].get(k) for k in ids)
                and e["metadata"].get("source_url", "").startswith("https://www.sec.gov/Archives/edgar/data/")
                for e in data["evidence"]
            ):
                return "FAIL", "Backend provenance invalid"
        return "PASS", "Real scoped retrieval accepted; no generated answer"
    if case in {"vector_structured", "vector_graph"}:
        route = [item["tool"] for item in data["retrieval_attempts"]]
        if route == expected.split("→") and data["used_tool"] == route[-1] and bool(data["evidence"]):
            return "PASS", "Real primary and alternate arms observed"
        if route == ["vector"] and data["used_tool"] == "vector":
            return "BLOCKED", "Real RAG returned eligible evidence; fallback trigger was not observed"
        return "FAIL", "Expected a single successful alternate backend"
    if case == "traversal":
        ok = not data["retrieval_attempts"] and not data["evidence"] and data["retrieval_limitation"]
    elif case == "quarter_clarify":
        ok = data["selected_tool"] == "clarification" and not data["retrieval_attempts"]
    elif case == "coverage_miss":
        ok = data["selected_tool"] == "direct_reply" and not data["retrieval_attempts"]
    else:
        attempt = data["retrieval_attempts"][0]
        ok = attempt.get("failure", {}).get("type") == "backend_unavailable" and attempt["retry_count"] == 1
    return ("PASS", "Expected safe handling observed") if ok else ("FAIL", "Expected safe handling was not observed")


def observed_coverage():
    import duckdb
    from graphrag import backends, graph_backend
    from neo4j import READ_ACCESS
    from rag.coverage import default_index

    rag = {(f.ticker, f.accession) for f in default_index().filings}
    with duckdb.connect(os.environ["MSFT_FACT_DB_PATH"], read_only=True) as conn:
        structured = set(conn.execute("select distinct ticker, accession_number from financial_facts_v1").fetchall())
        version = dict(conn.execute("select * from store_meta_v1").fetchall()).get("corpus_version")
    with graph_backend.connect().session(database=os.environ["NEO4J_DATABASE"], default_access_mode=READ_ACCESS) as session:
        graph = {(x["ticker"], x["accession"]) for x in session.run(
            "MATCH (c:Company)-[:FILES]->(f:Filing)-[:CONTAINS]->(:Section)-[:SUPPORTS]->(:Claim) "
            "RETURN DISTINCT c.ticker AS ticker, f.accession_number AS accession")}
    return {
        "registration": {k: v.split(":", 1)[0] for k, v in backends.status.items()},
        "structured_corpus_version": version,
        "filings": {k: len(v) for k, v in {"rag": rag, "graph": graph, "structured": structured}.items()},
        "tickers": {k: sorted({t for t, _ in v}) for k, v in {"rag": rag, "graph": graph, "structured": structured}.items()},
        "graph_only_filing_count": len(graph - rag), "structured_only_filing_count": len(structured - rag),
        "rag_only_filing_count": len(rag - graph - structured), "common_filing_count": len(rag & graph & structured),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--unavailable-child", action="store_true")
    args = parser.parse_args()
    os.environ.update(KPMG_GRAPHRAG_ENABLED="1", KPMG_QUERY_LLM_ENABLED="0", KPMG_ANSWER_ENABLED="0",
                      CYPHER_ARM_ENABLED="0")
    args.output.mkdir(parents=True, exist_ok=True)
    if args.unavailable_child:
        with TestClient(app) as client:
            print(json.dumps(request(client, *CASES[-1][:2])))
        return
    log = args.output / "joint-graphrag-traces.jsonl"
    with TestClient(app) as client, log.open("w") as sink:
        coverage = observed_coverage()
        (args.output / "observed-backend-coverage.json").write_text(json.dumps(coverage, indent=2)+"\n")
        for name, question, expected in CASES:
            if name == "unavailable":
                env = {k: v for k, v in os.environ.items() if not k.startswith("NEO4J_")}
                env.update(KPMG_CHROMA_WARMUP="0", KPMG_RAG_BACKEND="real")
                # A real, freshly registered GraphRAG module has no graph arm in this process.
                data = json.loads(subprocess.check_output(
                    [sys.executable, __file__, str(args.output), "--unavailable-child"], env=env, text=True,
                ))
            else:
                data = request(client, name, question)
            status, reason = verdict(name, expected, data)
            row = {
                "case": name, "question": question, "expected": expected, "outcome": status, "reason": reason,
                **{key: data.get(key) for key in ("trace_id", "status", "selected_tool", "used_tool", "filters",
                     "retrieval_attempts", "retrieval_failure", "retrieval_limitation", "latency_ms", "fallback_attempts")},
                "weak_reasons": data.get("weak_reasons", []),
                "rag_coverage": (data.get("joint_trace") or {}).get("precheck", {}).get("status"),
                "evidence": [{key: item["metadata"].get(key) for key in PROVENANCE} for item in data["evidence"]],
            }
            sink.write(json.dumps(row) + "\n")
            sink.flush()
            print(name, status, reason, flush=True)


if __name__ == "__main__":
    main()

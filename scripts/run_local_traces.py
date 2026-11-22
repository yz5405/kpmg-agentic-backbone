"""Compare top_k=10 and 15 over the same local API questions."""
import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

QUESTIONS = (
    "What was Microsoft's total revenue for the three months ended March 31, 2026?",
    "What was Microsoft's revenue in FY2026?",
    "What was Microsoft's net income in Q3 FY2026?",
    "What was Microsoft's operating income in Q3 FY2026?",
    "Compare Microsoft's and Apple's revenue in FY2026.",
    "Among the ten companies in the corpus, which reported the highest revenue in its latest fiscal year?",
    "Rank the ten companies by net margin for each company's latest fiscal year.",
    "Which company had the fastest revenue growth in its latest fiscal year?",
    "Summarize Microsoft's competition risk disclosures.",
    "What shared risks connect Microsoft and Apple?",
)

parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
parser.add_argument("--port", type=int, default=8765)
args = parser.parse_args()
endpoint = f"http://127.0.0.1:{args.port}/query"
with args.output.open("w", encoding="utf-8") as output:
    for index, question in enumerate(QUESTIONS, 1):
        for top_k in (10, 15):
            trace_id = f"v04-local-{index:02d}-{top_k}"
            request = Request(endpoint, data=json.dumps({
                "query": question, "top_k": top_k, "trace_id": trace_id,
            }).encode(), headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=120) as response:
                result = json.load(response)
            if result.get("llm_calls") or result.get("query_understanding_mode") == "llm":
                raise RuntimeError("This runner expects real retrieval with both LLM stages disabled")
            keys = (
                "status", "filters", "form", "selected_tool", "used_tool", "retrieval_attempts",
                "retrieval_limitation", "retrieval_failure", "evidence_status", "error",
                "fallback_attempts", "trace_id", "latency_ms", "llm_calls", "token_usage",
                "query_understanding_mode",
            )
            record = {key: result.get(key) for key in keys}
            record.update({"case": index, "question": question, "test_type": "real_local_retrieval_only",
                           "top_k": top_k, "evidence_count": len(result["evidence"]),
                           "citation_count": len(result["citations"]),
                           "chunk_ids": [c["chunk_id"] for c in result["citations"] if c.get("chunk_id")],
                           "accessions": sorted({c["accession_number"] for c in result["citations"] if c.get("accession_number")}),
                           "section_ids": [c["section_id"] for c in result["citations"] if c.get("section_id")],
                           "fact_ids": [c["fact_id"] for c in result["citations"] if c.get("fact_id")]})
            output.write(json.dumps(record) + "\n")
            output.flush()
print("Wrote 20 local retrieval traces.")

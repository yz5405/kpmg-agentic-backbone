"""Compare first and second real retrieval requests in two independent processes."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter


def measure(question, mode):
    from fastapi.testclient import TestClient

    from api.main import app

    start = perf_counter()
    with TestClient(app) as client:
        startup = round((perf_counter() - start) * 1000, 2)
        measurements = []
        for i in range(2):
            response = client.post("/query", json={"query": question, "top_k": 15, "trace_id": f"warmup-{mode}-{i}"})
            response.raise_for_status()
            result = response.json()
            trace = result["joint_trace"]
            if result["status"] != "SUCCESS" or not trace["accepted_count"] or result["llm_calls"]:
                raise RuntimeError("Expected real retrieval-only evidence")
            measurements.append({
                "api_ms": result["latency_ms"], "steps_ms": trace["latency_ms"],
                "accepted_count": trace["accepted_count"],
            })
        return {
            "mode": mode, "pid": os.getpid(), "service_startup_ms": startup,
            "warmup": result["chroma_warmup"], "first": measurements[0], "second": measurements[1],
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("question")
    parser.add_argument("--child", choices=("cold", "warmed"))
    args = parser.parse_args()
    if args.child:
        print(json.dumps(measure(args.question, args.child)))
        return
    if (os.getenv("KPMG_RAG_BACKEND"), os.getenv("RAG_BACKEND"), os.getenv("KPMG_COVERAGE_PRECHECK")) != ("real", "chroma", "1"):
        parser.error("Requires real Chroma with coverage pre-check enabled")
    results = []
    for mode in ("cold", "warmed"):
        env = {**os.environ, "KPMG_ANSWER_ENABLED": "0", "KPMG_QUERY_LLM_ENABLED": "0",
               "KPMG_CHROMA_WARMUP": "1" if mode == "warmed" else "0"}
        result = subprocess.check_output(
            [sys.executable, __file__, str(args.output), args.question, "--child", mode], env=env, text=True,
        )
        results.append(json.loads(result))
    if results[0]["pid"] == results[1]["pid"] or results[1]["warmup"]["status"] != "ready":
        raise RuntimeError("Expected independent processes and successful startup warm-up")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results))


if __name__ == "__main__":
    main()

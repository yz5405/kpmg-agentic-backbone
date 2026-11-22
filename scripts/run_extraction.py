"""Write one sanitized extraction record per Eval wording variant."""
import argparse
import json
import os
from pathlib import Path

from agent.llm_query_understanding import understand_query_llm

parser = argparse.ArgumentParser()
parser.add_argument("input", type=Path)
parser.add_argument("output", type=Path)
parser.add_argument("--mode", choices=("rules", "llm"), default="rules")
args = parser.parse_args()
if args.mode == "llm" and not os.getenv("OPENAI_API_KEY"):
    parser.error("LLM mode requires an approved, locally configured API credential")
os.environ["KPMG_QUERY_LLM_ENABLED"] = "1" if args.mode == "llm" else "0"
args.output.mkdir(parents=True, exist_ok=True)
count = fallback_count = 0
with args.input.open(encoding="utf-8") as source:
    for line in source:
        case = json.loads(line)
        identifier = str(case["vid"])
        if not identifier or not all(c.isascii() and (c.isalnum() or c in "-_~") for c in identifier):
            parser.error("Unsupported Eval variant ID")
        result = understand_query_llm(case["messy"])
        if args.mode == "llm" and result.get("query_understanding_mode") != "llm":
            fallback_count += 1
        record = {
            "variant_id": identifier, "case_id": case["qid"], "original_question": case["clean"],
            "question": case["messy"], "requested_mode": args.mode, "extraction": result,
        }
        (args.output / f"{identifier}.json").write_text(json.dumps(record) + "\n", encoding="utf-8")
        count += 1
print(f"Extraction records: {count}; LLM fallbacks: {fallback_count}")
if fallback_count:
    raise SystemExit(1)

"""KPMG Agentic Backbone — Single-Agent MVP Demo.

Run:
    python main.py

Default backend: mock.
Real backend: set KPMG_RAG_BACKEND=real and RAG_INDEX_DIR.

No LLM API key required.
"""

import os

from agent.integration import run_integrated_agent


DEMO_QUESTIONS = [
    (
        "Revenue Number",
        "What was Microsoft's total revenue "
        "for the three months ended March 31, 2026?",
    ),
    (
        "Revenue Drivers",
        "What drove Microsoft's revenue growth in Q3 FY2026?",
    ),
]


def display_result(name: str, question: str, result: dict):
    """Display workflow results and source provenance."""

    print("\n" + "=" * 70)
    print("KPMG AGENTIC BACKBONE — SINGLE-AGENT MVP")
    print("=" * 70)

    print("Test Case:", name)
    print("Question:", question)
    print("Backend:", os.getenv("KPMG_RAG_BACKEND", "mock"))
    print("Status:", result["status"])
    print("Filters:", result["filters"])
    print("Evidence Count:", len(result["evidence"]))
    print("Error:", result["error"])

    print("\n--- TOP RETRIEVED EVIDENCE ---")

    for rank, item in enumerate(result["evidence"][:3], start=1):
        metadata = item.get("metadata", {})

        print(f"\nEvidence {rank}")
        print("Ticker:", metadata.get("ticker"))
        print("Form:", metadata.get("form"))
        print("Section:", metadata.get("section"))
        print("Chunk ID:", metadata.get("chunk_id"))
        print("Source URL:", metadata.get("source_url"))

        snippet = " ".join(item.get("text", "").split())
        print("Text:", snippet[:600])

    if not result["evidence"]:
        print("No evidence retrieved.")

    print("\n--- EXECUTION LOGS ---")

    for log in result["logs"]:
        print(log)

    print("\nFinal Status:", result["status"])


def main():
    """Run two fixed Microsoft financial questions."""

    print("Starting Agentic Backbone MVP Demo...")

    for name, question in DEMO_QUESTIONS:
        result = run_integrated_agent(
            query=question,
            top_k=8,
        )

        display_result(name, question, result)

        if result["status"] != "SUCCESS":
            raise RuntimeError(
                f"Demo case '{name}' failed: "
                f"{result.get('error') or result['status']}"
            )

    print("\n" + "=" * 70)
    print("ALL MVP DEMO CASES COMPLETED SUCCESSFULLY")
    print("=" * 70)


if __name__ == "__main__":
    main()

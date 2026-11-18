
"""Compare targeted RAG retry with direct GraphRAG fallback.

Mock-only policy experiment; does not measure real retrieval accuracy.
"""

from time import perf_counter
import pytest


SCENARIOS = {
    "empty": {
        "initial": [],
        "retry": ["verified revenue evidence"],
        "graph": ["verified revenue evidence"],
    },
    "weak": {
        "initial": ["revenue increased"],
        "retry": ["verified revenue evidence"],
        "graph": ["verified revenue evidence"],
    },
    "evaluator_gap": {
        "initial": ["verified revenue evidence"],
        "retry": ["verified revenue evidence"],
        "graph": ["verified revenue evidence"],
    },
}


def evaluate(evidence, scenario):
    """A shared mock sufficiency rule for both strategies."""
    if scenario == "evaluator_gap":
        # Simulates an evaluator that cannot handle this query type.
        return False
    return "verified revenue evidence" in evidence


def run_strategy(scenario, strategy):
    fixture = SCENARIOS[scenario]
    calls = []
    start = perf_counter()

    calls.append("RAG")
    evidence = fixture["initial"]

    initial_sufficient = evaluate(evidence, scenario)

    if not initial_sufficient:
        if strategy == "targeted_retry":
            calls.append("RAG_RETRY")
            evidence = fixture["retry"]
        elif strategy == "direct_graphrag":
            calls.append("GraphRAG")
            evidence = fixture["graph"]

    sufficient = evaluate(evidence, scenario)
    latency_ms = (perf_counter() - start) * 1000

    return {
        "scenario": scenario,
        "strategy": strategy,
        "final_status": "SUCCESS" if sufficient else "NO_EVIDENCE",
        "evidence_sufficient": sufficient,
        "tool_calls": calls,
        "latency_ms": latency_ms,
    }


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize(
    "strategy", ["baseline", "targeted_retry", "direct_graphrag"]
)
def test_retry_comparison(scenario, strategy):
    result = run_strategy(scenario, strategy)

    print(
        f"\nScenario: {scenario}"
        f"\nStrategy: {strategy}"
        f"\nFinal Status: {result['final_status']}"
        f"\nEvidence Sufficiency: {result['evidence_sufficient']}"
        f"\nTool Calls: {result['tool_calls']}"
        f"\nLatency: {result['latency_ms']:.4f} ms"
    )

    if scenario == "evaluator_gap":
        assert result["final_status"] == "NO_EVIDENCE"
    elif strategy == "baseline":
        assert result["final_status"] == "NO_EVIDENCE"
    else:
        assert result["final_status"] == "SUCCESS"

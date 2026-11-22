import json
from copy import deepcopy

import httpx
import pytest

from agent.answer_node import AnswerGenerator, answer_generator_from_env
from agent.llm_client import ChatCompletionClient, Completion, CompletionError
from agent.graph_workflow import run_graph_agent
import agent.integration as integration

EVIDENCE = [{"text": "MSFT FY2026 revenue was 123 million USD.", "metadata": {
    "source_url": "https://www.sec.gov/Archives/example", "fact_id": "f1",
    "cell_key": "revenue:2026", "fiscal_year": 2026, "ticker": "MSFT"}}]
USAGE = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
STATE = {"query": "Microsoft revenue?", "status": "SUCCESS", "error": None,
         "evidence": EVIDENCE}


def completion(answer="Revenue was 123 million USD [1].", ids=None, status="SUCCESS", usage=USAGE):
    return Completion(json.dumps({"status": status, "answer": answer,
                                 "citation_ids": [1] if ids is None else ids}),
                      "actual-test-model", usage)


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def generator(client, attempts=2):
    return AnswerGenerator(client, model="requested-model", max_attempts=attempts,
                           retry_delay=0, sleep=lambda _: None)


def graph(client, **kwargs):
    return run_graph_agent(query="Microsoft revenue?", parser=lambda _: {},
                           retriever=lambda **_: EVIDENCE,
                           answer_generator=generator(client), **kwargs)


def test_answer_and_metadata_preservation():
    original = deepcopy(STATE)
    client = FakeClient(completion())
    result = generator(client)(STATE)
    assert result["status"] == "SUCCESS"
    assert result["model"] == "actual-test-model"
    assert result["llm_calls"] == 1
    assert result["token_usage"] == USAGE
    assert result["citations"] == [{**EVIDENCE[0]["metadata"], "evidence_id": 1}]
    assert STATE == original
    result["citations"][0]["fact_id"] = "changed"
    assert EVIDENCE[0]["metadata"]["fact_id"] == "f1"


@pytest.mark.parametrize("status,evidence,error", [
    ("NO_EVIDENCE", [], None), ("SUCCESS", [], None),
    ("ERROR", EVIDENCE, "retrieval failed"),
])
def test_skip_without_supported_evidence(status, evidence, error):
    client = FakeClient()
    result = generator(client)({**STATE, "status": status, "evidence": evidence, "error": error})
    assert result["llm_calls"] == 0
    assert result["token_usage"] is None
    assert result["citations"] == []
    assert not client.calls


@pytest.mark.parametrize("bad", [
    Completion("not JSON", "m", USAGE),
    completion(ids=[2]), completion(ids=[True]), completion(ids=["1"]),
    completion(answer="Uncited claim", ids=[1]),
    completion(answer="Wrong reference [2]", ids=[1]),
    completion(status="HALLUCINATED"),
])
def test_invalid_outputs_fail_closed(bad):
    result = generator(FakeClient(bad), attempts=1)(STATE)
    assert result["status"] == "ERROR"
    assert result["answer"] is None
    assert result["citations"] == []
    assert result["llm_calls"] == 1
    assert result["token_usage"] == USAGE


def test_retry_validation_aggregates_usage():
    result = generator(FakeClient(Completion("bad JSON", "model", USAGE), completion()))(STATE)
    assert result["status"] == "SUCCESS"
    assert result["llm_calls"] == 2
    assert result["token_usage"] == {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30}


def test_retry_transport_leaves_unknown_usage_null():
    result = generator(FakeClient(CompletionError("timeout", retryable=True), completion()))(STATE)
    assert result["status"] == "SUCCESS"
    assert result["llm_calls"] == 2
    assert result["token_usage"] is None


def test_permanent_failure_not_retried_or_leaked():
    client = FakeClient(CompletionError("secret API key"))
    result = generator(client)(STATE)
    assert result["status"] == "ERROR"
    assert result["llm_calls"] == 1
    assert "secret" not in str(result)
    assert result["model"] is None


def test_missing_usage_is_null():
    assert generator(FakeClient(completion(usage=None)))(STATE)["token_usage"] is None


def test_model_abstention():
    result = generator(FakeClient(completion(answer="Unsupported guess", ids=[], status="NO_EVIDENCE")))(STATE)
    assert result["status"] == "NO_EVIDENCE"
    assert result["answer"] == "Insufficient evidence to answer this question."
    assert result["citations"] == []
    assert result["llm_calls"] == 1


def test_context_limit_skips_llm():
    client = FakeClient()
    result = AnswerGenerator(client, model="test", max_context_chars=1)(STATE)
    assert result["status"] == "ERROR"
    assert result["llm_calls"] == 0


def test_real_graph_retains_answer_fields():
    result = graph(FakeClient(completion()))
    assert result["answer"] == "Revenue was 123 million USD [1]."
    assert result["model"] == "actual-test-model"
    assert result["token_usage"] == USAGE
    assert result["citations"][0]["fact_id"] == "f1"
    assert result["evidence"] == EVIDENCE


def test_fallback_generation_uses_final_selected_evidence():
    client = FakeClient(completion())
    result = run_graph_agent(
        query="Microsoft revenue?", parser=lambda _: {},
        retriever=lambda **_: {"evidence": [], "evidence_status": "empty", "weak_reasons": []},
        graphrag_retriever=lambda **_: EVIDENCE,
        evidence_evaluator=lambda **kw: kw["graphrag_evidence"],
        answer_generator=generator(client),
    )
    assert result["status"] == "SUCCESS"
    assert result["llm_calls"] == 1
    assert json.loads(client.calls[0]["messages"][1]["content"])["evidence"][0]["text"] == EVIDENCE[0]["text"]


def test_fallback_cannot_generate_without_evaluation():
    with pytest.raises(ValueError, match="requires an evidence evaluator"):
        graph(FakeClient(), graphrag_retriever=lambda **_: EVIDENCE)


def test_evaluator_rejection_skips_generation():
    client = FakeClient()
    result = graph(client, evidence_evaluator=lambda **_: [])
    assert result["status"] == "NO_EVIDENCE"
    assert result["llm_calls"] == 0


def test_graph_parser_failure_skips_generation():
    client = FakeClient()
    def fail(_):
        raise ValueError("bad query")
    result = run_graph_agent(query="x", parser=fail, retriever=lambda **_: EVIDENCE,
                             answer_generator=generator(client))
    assert result["status"] == "ERROR"
    assert result["error"] == "Query parsing failed."
    assert result["llm_calls"] == 0


def test_integrated_entry_point(monkeypatch):
    monkeypatch.setattr(integration, "retrieve_evidence_result", lambda **_: EVIDENCE)
    result = integration.run_integrated_agent("Microsoft revenue?",
                                             answer_generator=generator(FakeClient(completion())))
    assert result["status"] == "SUCCESS"
    assert result["answer"].endswith("[1].")
    assert result["llm_calls"] == 1


def test_environment_opt_in(monkeypatch):
    monkeypatch.delenv("KPMG_ANSWER_ENABLED", raising=False)
    assert answer_generator_from_env() is None
    monkeypatch.setenv("KPMG_ANSWER_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("KPMG_ANSWER_MODEL", "explicit-model")
    assert answer_generator_from_env().model == "explicit-model"
    monkeypatch.delenv("KPMG_ANSWER_MODEL")
    with pytest.raises(ValueError, match="Answer generation is not configured"):
        answer_generator_from_env()


def test_transport_and_usage_without_live_network():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"model": "actual-test-model",
            "choices": [{"finish_reason": "stop", "message": {"content": completion().content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
    client = ChatCompletionClient(api_key="fake-key", base_url="https://example.invalid/v1",
                                  transport=httpx.MockTransport(handler))
    result = generator(client)(STATE)
    assert result["status"] == "SUCCESS"
    assert result["token_usage"] == USAGE
    assert len(requests) == result["llm_calls"] == 1
    assert str(requests[0].url) == "https://example.invalid/v1/chat/completions"
    assert json.loads(requests[0].content)["model"] == "requested-model"


@pytest.mark.parametrize("status,expected_calls", [(429, 2), (500, 2), (401, 1)])
def test_transport_retry_accounting(status, expected_calls):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={"error": {"message": "secret"}})
    client = ChatCompletionClient(api_key="fake-key", transport=httpx.MockTransport(handler))
    result = generator(client)(STATE)
    assert result["status"] == "ERROR"
    assert result["llm_calls"] == len(requests) == expected_calls
    assert result["token_usage"] is None
    assert "secret" not in str(result)


def test_truncated_provider_response_retains_known_usage():
    def handler(request):
        return httpx.Response(200, json={"model": "actual-test-model",
            "choices": [{"finish_reason": "length", "message": {"content": "truncated"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
    client = ChatCompletionClient(api_key="fake-key", transport=httpx.MockTransport(handler))
    result = generator(client)(STATE)
    assert result["status"] == "ERROR"
    assert result["answer"] is None
    assert result["llm_calls"] == 1
    assert result["model"] == "actual-test-model"
    assert result["token_usage"] == USAGE


def test_answer_accounting_is_per_request():
    client = FakeClient(completion(), completion(usage=None))
    node = generator(client)
    first = node(STATE)
    second = node(STATE)
    assert first["llm_calls"] == second["llm_calls"] == 1
    assert first["token_usage"] == USAGE
    assert second["token_usage"] is None


@pytest.mark.parametrize("fallback_evidence", [EVIDENCE, []])
def test_evaluator_rejection_attempts_fallback_once(fallback_evidence):
    calls = []

    def fallback(**request):
        calls.append(request)
        return fallback_evidence

    result = run_graph_agent(
        query="Microsoft revenue?",
        parser=lambda _: {},
        retriever=lambda **_: {"evidence": EVIDENCE, "evidence_status": "ok", "weak_reasons": []},
        graphrag_retriever=fallback,
        evidence_evaluator=lambda **state: state["graphrag_evidence"],
    )

    assert len(calls) == 1
    assert result["should_try_graphrag"]
    assert result["evidence"] == fallback_evidence
    assert result["status"] == ("SUCCESS" if fallback_evidence else "NO_EVIDENCE")


def test_financial_evaluator_reads_frozen_markdown_income_statement():
    from agent.routing import evaluate_financial_evidence

    evidence = {
        "text": (
            "ITEM 1. FINANCIAL STATEMENTS\n"
            "INCOME STATEMENTS\n"
            "(In millions, except per share amounts) (Unaudited)\n"
            "|  | Three Months Ended March 31, 2026 | Three Months Ended March 31, 2025 | "
            "Nine Months Ended March 31, 2026 | Nine Months Ended March 31, 2025 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| Total revenue | 82,886 | 70,066 | 241,832 | 205,283 |"
        ),
        "metadata": {
            "source_url": "https://www.sec.gov/Archives/example",
            "ticker": "MSFT",
            "fiscal_year": 2026,
            "fiscal_period": "Q3",
            "reporting_period_end": "2026-03-31",
            "is_table": True,
        },
    }
    args = {
        "query": "What was Microsoft's total revenue for the three months ended March 31, 2026?",
        "graphrag_evidence": [],
        "evidence_status": "ok",
        "weak_reasons": [],
    }

    assert evaluate_financial_evidence(rag_evidence=[evidence], **args) == [evidence]
    wrong_date = {**evidence, "text": evidence["text"].replace("March 31", "March 30")}
    assert evaluate_financial_evidence(rag_evidence=[wrong_date], **args) == []

from unittest.mock import Mock

from fastapi.testclient import TestClient

from agent.answer_node import AnswerGenerator
from agent.joint_evidence import financial_inputs, quarter_cloud_evidence
from agent.graph_workflow import run_graph_agent
from agent.chroma_warmup import warm_chroma
from api.main import app
from tests.test_answer_generation import FakeClient, completion

META = {"ticker": "MSFT", "form": "10-Q", "reporting_period_end": "2026-03-31",
        "fiscal_period": "Q3", "fiscal_year": 2026, "section_title": "Management Discussion and Analysis",
        "source_url": "https://www.sec.gov/Archives/edgar/data/789019/000119312526191507/msft.htm",
        "accession_number": "0001193125-26-191507"}

TABLE = """(In millions)
| | Three Months Ended March 31, 2026 | Three Months Ended March 31, 2025 | Nine Months Ended March 31, 2026 |
| --- | --- | --- | --- |
| Intelligent Cloud | | | |
| Revenue | $34,681 | $26,751 | $98,485 |
| Total | | | |
| Revenue | $82,886 | $70,066 | $241,832 |"""


def evidence(chunk, text, **metadata):
    return {"text": text, "metadata": {**META, "chunk_id": chunk, **metadata}}


def test_financial_validation_retains_consolidated_quarter_only():
    valid = evidence("q", TABLE, is_table=True)
    alternatives = [
        evidence("wrong-period", TABLE.replace("Three Months", "Nine Months"), is_table=True),
        evidence("wrong-unit", TABLE.replace("millions", "thousands"), is_table=True),
        evidence("wrong-metric", TABLE.replace("Revenue", "Operating income"), is_table=True),
        evidence("wrong-filing-date", TABLE, is_table=True, reporting_period_end="2026-06-30"),
        evidence("segment-only", TABLE.split("| Total")[0], is_table=True),
    ]
    rows = financial_inputs([*alternatives, valid], "Calculate YoY revenue", ["2026-03-31"])
    assert [row["metadata"]["chunk_id"] for row in rows] == ["q"]
    assert rows[0]["metadata"]["verified_financial_input"]["as_reported"] == "$82,886"


def test_blocked_calculation_preserves_evidence_without_model_call():
    rows = [evidence("q", TABLE, is_table=True)]
    generate = Mock(side_effect=AssertionError("blocked calculation reached the model"))
    result = run_graph_agent(
        query="Calculate revenue growth", parser=lambda _: {}, retriever=Mock(),
        joint_retrieval=lambda _: {"status": "SUCCESS", "evidence": rows,
                                   "calculation_status": "blocked", "calculation_reason": "unsupported_calculation"},
        answer_generator=generate,
    )
    assert result["evidence"] == rows and result["answer"] is None
    generate.assert_not_called()


def test_period_selection_and_answer_citation_are_independent():
    quarter = "Intelligent Cloud\n\nRevenue increased 30%, driven by Azure.\n\nOperating income increased."
    nine = quarter.replace("30%", "29%")
    rows = [
        evidence("C1-0091", "Nine Months Ended March 31, 2026\n\n" + nine, parent_text=""),
        evidence("C1-0092", nine, parent_text="Nine Months Ended March 31, 2026\n\n" + nine),
        evidence("C1-0087", quarter, parent_text="Three Months Ended March 31, 2026 Compared with Three Months Ended March 31, 2025\n\n" + quarter),
        evidence("C1-0089", TABLE, is_table=True),
        evidence("C1-0072", TABLE, is_table=True),
    ]
    selected = quarter_cloud_evidence(rows, ["2026-03-31"])
    assert [row["metadata"]["chunk_id"] for row in selected] == ["C1-0087", "C1-0089", "C1-0072"]
    assert all("98,485" not in row["text"] and "29%" not in row["text"] and "parent_text" not in row["metadata"] for row in selected)
    fake = FakeClient(completion("Azure drove growth [2].", ids=[2]), completion("Azure drove growth [1].", ids=[1]))
    result = AnswerGenerator(fake, model="test")({"query": "What drove growth?", "evidence": selected})
    assert len(fake.calls) == 2
    assert [citation["chunk_id"] for citation in result["citations"]] == ["C1-0087"]


def test_startup_warmup_failure_preserves_health(monkeypatch, tmp_path):
    monkeypatch.setenv("KPMG_CHROMA_WARMUP", "1")
    monkeypatch.setenv("KPMG_RAG_BACKEND", "real")
    monkeypatch.setenv("RAG_BACKEND", "chroma")
    monkeypatch.setenv("RAG_CHROMA_DIR", str(tmp_path))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert app.state.chroma_warmup["status"] == "failed"


def test_warmup_respects_local_embedding_allowlist(monkeypatch, tmp_path):
    monkeypatch.setenv("KPMG_CHROMA_WARMUP", "1")
    monkeypatch.setenv("KPMG_RAG_BACKEND", "real")
    monkeypatch.setenv("RAG_BACKEND", "chroma")
    monkeypatch.setenv("RAG_CHROMA_DIR", str(tmp_path))
    (tmp_path / "meta.json").write_text('{"embedder":"openai:example"}')
    assert warm_chroma()["status"] == "skipped"

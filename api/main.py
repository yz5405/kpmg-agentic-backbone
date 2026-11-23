import os
import uuid
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from agent.answer_node import AnswerConfigurationError
from agent.chroma_warmup import warm_chroma
from agent.integration import run_integrated_agent
from agent.tools.rag_tool import retrieve_evidence_result
from agent.routing import evaluate_financial_evidence
from agent.query_parser import understand_query
from agent.tool_selection import select_tool
from agent.tools.graphrag_tool import retrieve_graph_evidence, retrieve_structured_evidence

@asynccontextmanager
async def lifespan(application):
    application.state.chroma_warmup = await run_in_threadpool(warm_chroma)
    yield


app = FastAPI(
    title="KPMG Agentic Backbone API",
    version="0.2.0",
    lifespan=lifespan,
)


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=15, ge=1, le=50)
    trace_id: str | None = None

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/explorer", include_in_schema=False)
def financial_explorer():
    configured = os.getenv("KPMG_EXPLORER_HTML")
    if not configured or not Path(configured).is_file():
        raise HTTPException(status_code=404, detail="Financial Explorer is not configured")
    return FileResponse(configured, media_type="text/html")


def _evaluate_legacy_fallback(**inputs):
    query = inputs["query"]
    _, intent = select_tool(query, None, understand_query(query))
    if intent == "narrative":
        return inputs["rag_evidence"] or inputs["graphrag_evidence"]
    if intent == "financial":
        return evaluate_financial_evidence(**inputs)
    return []


@app.post("/query")
def query_agent(request: QueryRequest):
    start = perf_counter()
    trace_id = request.trace_id or str(uuid.uuid4())
    workflow_options = {"trace_id": trace_id}
    default_mode = "legacy" if os.getenv("KPMG_GRAPHRAG_ARM") else "auto"
    if os.getenv("KPMG_GRAPHRAG_ENABLED") == "1" and os.getenv("KPMG_TOOL_SELECTION", default_mode) == "auto":
        workflow_options = {
            "tools": {"vector": retrieve_evidence_result, "structured": retrieve_structured_evidence,
                      "graph": retrieve_graph_evidence},
            "trace_id": trace_id,
        }
    elif os.getenv("KPMG_GRAPHRAG_ENABLED") == "1":
        retrievers = {
            "graph": retrieve_graph_evidence,
            "structured": retrieve_structured_evidence,
        }
        arm = os.getenv("KPMG_GRAPHRAG_ARM", "structured")
        if arm not in retrievers:
            raise HTTPException(status_code=503, detail="Invalid KPMG_GRAPHRAG_ARM configuration")
        workflow_options = {
            "graphrag_retriever": partial(retrievers[arm], trace_id=trace_id),
            "evidence_evaluator": _evaluate_legacy_fallback,
            "trace_id": trace_id,
            "fallback_tool": arm,
        }

    try:
        result = run_integrated_agent(
            query=request.query,
            top_k=request.top_k,
            **workflow_options,
        )
    except AnswerConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None

    citations = result.get("citations") or []
    retrieval_citations = []
    if not citations and result.get("status") == "SUCCESS" and not result.get("answer"):
        for item in result.get("evidence", []):
            metadata = item.get("metadata", {})
            source_url = metadata.get("source_url")
            if source_url:
                provenance = {
                    key: metadata[key]
                    for key in ("section_id", "fact_id", "chunk_id", "accession_number", "section", "section_title", "claim_id", "retrieval_method", "trace_id")
                    if metadata.get(key) is not None
                }
                retrieval_citations.append({
                    **provenance,
                    "source_url": source_url,
                    "ticker": metadata.get("ticker"),
                    "form": metadata.get("form"),
                    "fiscal_year": metadata.get("fiscal_year"),
                    "fiscal_period": metadata.get("fiscal_period"),
                    "reporting_period_end": metadata.get("reporting_period_end"),
                })

    if result.get("joint_trace") is None:
        citations = citations or retrieval_citations

    return {
        "query": request.query,
        "calculation_status": result.get("calculation_status", "not_required"),
        "calculation_reason": result.get("calculation_reason"),
        "chroma_warmup": getattr(app.state, "chroma_warmup", None),
        "retrieval_citations": retrieval_citations,
        "joint_trace": result.get("joint_trace"),
        "query_understanding_ms": result.get("query_understanding_ms"),
        "answer_ms": result.get("answer_ms"),
        "selected_tool": result.get("selected_tool", "vector"),
        "used_tool": result.get("used_tool"),
        "retrieval_attempts": result.get("retrieval_attempts", []),
        "retrieval_failure": result.get("retrieval_failure"),
        "retrieval_limitation": result.get("retrieval_limitation"),
        "fallback_attempts": max(0, len(result.get("retrieval_attempts", [])) - 1),
        "latency_ms": round((perf_counter() - start) * 1000, 2),
    "trace_id": trace_id,
        "status": result.get("status"),
    "evidence_status": result.get("evidence_status"),
    "weak_reasons": result.get("weak_reasons", []),
    "fallback_triggered": result.get("should_try_graphrag", False),
    "fallback_used": bool(len(result.get("retrieval_attempts", [])) > 1
                              and result.get("used_tool") == result["retrieval_attempts"][-1]["tool"]),
        "filters": result.get("filters", {}),
        "form": result.get("form"),
        "answer": result.get("answer"),
        "query_understanding_mode": result.get("query_understanding_mode"),
        "model": result.get("model"),
        "llm_calls": result.get("llm_calls", 0),
        "token_usage": result.get("token_usage"),
        "evidence": result.get("evidence", []),
    "citations": citations,
        "logs": result.get("logs", []),
        "error": result.get("error")
    }

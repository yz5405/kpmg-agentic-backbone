import os
import uuid
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent.integration import run_integrated_agent
from agent.tools.rag_tool import retrieve_evidence_result
from agent.routing import evaluate_financial_evidence
from agent.tools.graphrag_tool import retrieve_graph_evidence, retrieve_structured_evidence

app = FastAPI(
    title="KPMG Agentic Backbone API",
    version="0.2.0"
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


@app.post("/query")
def query_agent(request: QueryRequest):
    start = perf_counter()
    trace_id = request.trace_id or str(uuid.uuid4())
    workflow_options = {}
    if os.getenv("KPMG_GRAPHRAG_ENABLED") == "1" and os.getenv("KPMG_TOOL_SELECTION") == "auto":
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
            "graphrag_retriever": retrievers[arm],
            "evidence_evaluator": evaluate_financial_evidence,
        }

    result = run_integrated_agent(
        query=request.query,
        top_k=request.top_k,
        **workflow_options,
    )

    citations = result.get("citations") or []
    if not citations and result.get("status") == "SUCCESS" and not result.get("answer"):
        for item in result.get("evidence", []):
            metadata = item.get("metadata", {})
            source_url = metadata.get("source_url")
            if source_url:
                provenance = {
                    key: metadata[key]
                    for key in ("section_id", "fact_id", "chunk_id", "accession_number")
                    if metadata.get(key) is not None
                }
                citations.append({
                    **provenance,
                    "source_url": source_url,
                    "ticker": metadata.get("ticker"),
                    "form": metadata.get("form"),
                    "fiscal_year": metadata.get("fiscal_year"),
                    "fiscal_period": metadata.get("fiscal_period"),
                    "reporting_period_end": metadata.get("reporting_period_end"),
                })

    return {
        "query": request.query,
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
    "fallback_used": bool(result.get("graphrag_evidence")) or (result.get("used_tool") is not None and len(result.get("retrieval_attempts", [])) > 1),
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

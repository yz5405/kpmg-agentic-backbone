import os
import uuid

from fastapi import FastAPI
from pydantic import BaseModel, Field

from agent.integration import run_integrated_agent
from agent.routing import evaluate_financial_evidence
from agent.tools.graphrag_tool import retrieve_structured_evidence

app = FastAPI(
    title="KPMG Agentic Backbone API",
    version="0.2.0"
)


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=10, ge=1, le=50)
    trace_id: str | None = None

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query")
def query_agent(request: QueryRequest):
    trace_id = request.trace_id or str(uuid.uuid4())
    workflow_options = {}
    if os.getenv("KPMG_GRAPHRAG_ENABLED") == "1":
        workflow_options = {
            "graphrag_retriever": retrieve_structured_evidence,
            "evidence_evaluator": evaluate_financial_evidence,
        }

    result = run_integrated_agent(
        query=request.query,
        top_k=request.top_k,
        **workflow_options,
    )

    citations = []
    for item in result.get("evidence", []):
        metadata = item.get("metadata", {})
        source_url = metadata.get("source_url")
        if source_url:
            citations.append({
                "source_url": source_url,
                "ticker": metadata.get("ticker"),
                "form": metadata.get("form"),
                "fiscal_year": metadata.get("fiscal_year"),
                "fiscal_period": metadata.get("fiscal_period"),
            })

    return {
        "query": request.query,
	"trace_id": trace_id,
        "status": result.get("status"),
	"evidence_status": result.get("evidence_status"),
	"weak_reasons": result.get("weak_reasons", []),
	"fallback_triggered": result.get("should_try_graphrag", False),
	"fallback_used": bool(result.get("graphrag_evidence")),
        "filters": result.get("filters", {}),
        "answer": None,
        "evidence": result.get("evidence", []),
	"citations": citations,
        "logs": result.get("logs", []),
        "error": result.get("error")
    }

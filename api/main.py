import os

from fastapi import FastAPI
from pydantic import BaseModel, Field

from agent.integration import run_integrated_agent
from agent.routing import evaluate_financial_evidence
from agent.tools.graphrag_tool import retrieve_structured_evidence

app = FastAPI(
    title="KPMG Agentic Backbone API",
    version="0.1.0"
)


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=8, ge=1, le=50)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query")
def query_agent(request: QueryRequest):
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

    return {
        "query": request.query,
        "status": result.get("status"),
        "filters": result.get("filters", {}),
        "answer": None,
        "evidence": result.get("evidence", []),
        "logs": result.get("logs", []),
        "error": result.get("error")
    }

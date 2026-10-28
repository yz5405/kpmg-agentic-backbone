from fastapi import FastAPI
from pydantic import BaseModel, Field

from agent.integration import run_integrated_agent

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
    result = run_integrated_agent(
        query=request.query,
        top_k=request.top_k
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

from fastapi import FastAPI, HTTPException
from pathlib import Path
import os
from typing import Literal
from pydantic import BaseModel, Field, StrictInt, field_validator
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from agent.integration import run_unified_agent

app = FastAPI(
    title="KPMG Agentic Backbone API",
    version="0.1.0"
)

app.add_middleware(CORSMiddleware,
    allow_origins=[v.strip() for v in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",") if v.strip()],
    allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: StrictInt = Field(default=8, ge=1, le=50)
    strategy: Literal["routed", "combined"] = "routed"
    trace_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("query")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


@app.get("/", include_in_schema=False)
def demo():
    return FileResponse(Path(__file__).parent / "demo.html")


@app.get("/explorer", include_in_schema=False)
def financial_explorer():
    return FileResponse(Path(__file__).parent / "explorer.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query")
def query_agent(request: QueryRequest):
    try:
        result = run_unified_agent(
            query=request.query,
            top_k=request.top_k, strategy=request.strategy, trace_id=request.trace_id
        )
    except (ValueError, ImportError) as exc:
        raise HTTPException(status_code=503, detail="Agent configuration is unavailable. Check server configuration.") from exc

    return {
        "query": request.query,
        "status": result.get("status"),
        "filters": result.get("filters", {}),
        "answer": result.get("answer"),
        "answer_mode": result.get("answer_mode"),
        "trace_id": result.get("trace_id"),
        "plan": result.get("plan"),
        "citations": result.get("citations", []),
        "warnings": result.get("warnings", []),
        "evidence": result.get("evidence", []),
        "logs": result.get("logs", []),
        "error": result.get("error")
    }


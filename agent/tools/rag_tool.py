"""RAG retrieval tool integration (Module 2 — owner: Jiahui Yang).

Adapter between the RAG Team's ``retrieve()`` (Retrieval API Contract v0,
https://github.com/Rachel-xs/KPMG_RAG/tree/contract-v0) and the Agent workflow.
See docs/function_contractsv2_cn.md §5.

Backend
-------
Default: the RAG Team's mock retriever, vendored unchanged in
``agent/tools/mock_retriever.py``.

Real retriever (RAG Team README):

    export PYTHONPATH=/path/to/KPMG_RAG:$PYTHONPATH
    export RAG_INDEX_DIR=/path/to/KPMG_RAG/data/index
    export KPMG_RAG_BACKEND=real

Behavior
--------
- query / filters / top_k are passed to RAG unchanged; RAG validates them.
- ``top_k <= 0`` raises ValueError (Agent contract requirement).
- No matches -> ``[]``.
- Exceptions from the retriever propagate unchanged.
"""

import os
from typing import Literal, TypedDict


class RetrievalResult(TypedDict):
    evidence: list[dict]
    evidence_status: Literal["ok", "weak", "empty"] | None
    weak_reasons: list[str]


def _load_retriever():
    """Prefer the status-aware real RAG entry point when available."""
    if os.getenv("KPMG_RAG_BACKEND", "mock") == "real":
        from importlib import import_module

        backend = import_module("rag.retrieve")
        return getattr(backend, "retrieve_with_status", backend.retrieve)

    from agent.tools.mock_retriever import retrieve

    return retrieve


def _to_evidence(chunk: dict) -> dict:
    """RetrievedChunk -> {"text", "metadata"} with all RAG fields kept as-is."""
    metadata = {key: value for key, value in chunk.items() if key not in ("text", "metadata")}
    metadata.update(chunk["metadata"])
    metadata["source"] = chunk["form"]  # Agent contract name for the filing type
    return {"text": chunk["text"], "metadata": metadata}



def retrieve_evidence(
    query: str,
    filters: dict | None = None,
    top_k: int = 10,
) -> list[dict]:
    """Retrieve and normalize SEC filing evidence as a list."""
    return retrieve_evidence_result(query, filters, top_k)["evidence"]


def retrieve_evidence_result(
    query: str,
    filters: dict | None = None,
    top_k: int = 10,
) -> RetrievalResult:
    """Normalize evidence and carry the RAG team's optional retrieval signals."""

    # Validate retrieval parameters
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise ValueError("top_k must be a positive integer")

    if top_k < 1:
        raise ValueError("top_k must be greater than zero")

    if top_k > 50:
        raise ValueError("top_k must be <= 50")

    # Select Mock or Real Retriever
    retrieve = _load_retriever()

    # Execute retrieval
    response = retrieve(query=query, filters=filters, top_k=top_k)
    if isinstance(response, list):
        return {
            "evidence": [_to_evidence(chunk) for chunk in response],
            "evidence_status": None,
            "weak_reasons": [],
        }

    # The v1.1 envelope uses results. Accept the earlier prototype shape too.
    chunks = response["results"] if "results" in response else response["chunks"]
    return {
        "evidence": [_to_evidence(chunk) for chunk in chunks],
        "evidence_status": response.get("evidence_status"),
        "weak_reasons": response.get("weak_reasons", []),
    }

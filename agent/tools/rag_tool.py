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

v1.2 (opt-in): ``retrieve_multi_evidence_result()`` wraps RAG ``retrieve_multi()`` for
multi-company / multi-filing filters. The default path and ``top_k=10`` are unchanged.
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


# ---------------------------------------------------------------- v1.2 retrieve_multi (opt-in)
class MultiRetrievalResult(RetrievalResult):
    subqueries: list[dict]
    skipped: list
    warnings: list[str]


MOCK_MULTI_WARNING = "mock backend: retrieve_multi is not available, ran a single search"


def retrieve_multi_evidence_result(
    query: str,
    filters: dict | None = None,
    top_k: int = 10,
    *,
    subqueries: list[dict] | None = None,
    top_k_each: int | None = None,
) -> MultiRetrievalResult:
    """Opt-in adapter for RAG Contract v1.2 ``retrieve_multi()``.

    Use for filters that list several tickers, forms, fiscal years or fiscal periods
    (e.g. ``{"ticker": ["MSFT", "AAPL"]}``). With single-valued filters RAG runs exactly
    one search, identical to ``retrieve_with_status()``.

    Same call and same keys as ``retrieve_evidence_result()``, so it can be passed to the
    workflow as ``retriever=``; adds ``subqueries``, ``skipped`` and ``warnings``.
    Each evidence item keeps ``metadata.subquery`` / ``metadata.subquery_rank``.
    The merged list can be longer than ``top_k`` (``top_k_each`` per target).

    Mock backend: the RAG mock has no ``retrieve_multi``; one search is run and a warning
    is returned, so mock results never look like a real multi-target split.
    """
    if os.getenv("KPMG_RAG_BACKEND", "mock") != "real":
        result = retrieve_evidence_result(query, filters, top_k)
        return {**result, "subqueries": [], "skipped": [], "warnings": [MOCK_MULTI_WARNING]}

    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 50:
        raise ValueError("top_k must be an integer between 1 and 50")

    from importlib import import_module

    retrieve_multi = getattr(import_module("rag.retrieve"), "retrieve_multi", None)
    if retrieve_multi is None:
        raise ImportError("rag.retrieve.retrieve_multi not found: RAG Contract v1.2 or later is required")

    response = retrieve_multi(
        query=query, filters=filters, top_k=top_k, subqueries=subqueries, top_k_each=top_k_each
    )
    return {
        "evidence": [_to_evidence(chunk) for chunk in response["results"]],
        "evidence_status": response.get("evidence_status"),
        "weak_reasons": response.get("weak_reasons", []),
        "subqueries": response.get("subqueries", []),
        "skipped": response.get("skipped", []),
        "warnings": response.get("warnings", []),
    }

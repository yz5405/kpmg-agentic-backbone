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


def _load_retriever():
    """Return RAG's ``retrieve`` function (mock by default)."""
    if os.getenv("KPMG_RAG_BACKEND", "mock") == "real":
        from rag.retrieve import retrieve
    else:
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
    top_k: int = 8,
) -> list[dict]:
    """Retrieve and normalize SEC filing evidence."""

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
    chunks = retrieve(
        query=query,
        filters=filters,
        top_k=top_k,
    )

    # Preserve text and citation metadata
    return [_to_evidence(chunk) for chunk in chunks]

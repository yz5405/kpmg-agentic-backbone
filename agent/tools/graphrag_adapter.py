
"""Temporary GraphRAG Mock Adapter.

Provides a LangGraph-compatible retrieval interface.
Replace the mock implementation when the GraphRAG API is ready.
"""


def retrieve_graph_evidence(
    query: str,
    filters: dict,
    top_k: int = 8,
) -> list[dict]:
    """Return simulated GraphRAG evidence."""

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be non-empty")

    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
        raise ValueError("top_k must be positive")

    filters = filters or {}

    # Only Microsoft is supported in this temporary mock.
    if filters.get("ticker") != "MSFT":
        return []

    mock_evidence = [
        {
            "text": (
                "Mock relationship: Azure growth contributed "
                "to Intelligent Cloud revenue growth."
            ),
            "metadata": {
                "ticker": "MSFT",
                "source_url": None,
                "chunk_id": "mock_graph_001",
                "retrieval_method": "graphrag_mock",
            },
        }
    ]

    return mock_evidence[:top_k]

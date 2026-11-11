
"""Rule-based tool routing for RAG and GraphRAG."""

import re


GRAPH_PATTERNS = [
    r"\brelat(?:e|ed|es|ionship|ionships)\b",
    r"\bconnect(?:ed|ion|ions|s)?\b",
    r"\bdepend(?:s|ency|encies|ent)?\b",
    r"\bcontribut(?:e|es|ed|ion|ions)\b",
    r"\b(?:drive|drives|driven|driving|drove)\b",
]


def select_retrieval_tool(query: str) -> str:
    """Select RAG or GraphRAG based on the query."""

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be non-empty")

    for pattern in GRAPH_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            return "graphrag"

    return "rag"


def make_routed_retriever(rag_retriever, graphrag_retriever):
    """Create a retriever compatible with LangGraph."""

    def routed_retriever(*, query, filters, top_k):
        selected = select_retrieval_tool(query)

        if selected == "graphrag":
            retriever = graphrag_retriever
        else:
            retriever = rag_retriever

        return retriever(
            query=query,
            filters=filters,
            top_k=top_k,
        )

    return routed_retriever

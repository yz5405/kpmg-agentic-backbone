"""Adapters for the GraphRAG team's actual contract, including its official mocks."""
import importlib
import os
from agent.tools.rag_tool import _to_evidence


def retrieve_graph(query, filters=None, top_k=8, trace_id=None, *, tool="graph_search"):
    if tool not in {"graph_search", "structured_search"}:
        raise ValueError("Unknown GraphRAG tool")
    mode = os.getenv("KPMG_GRAPH_BACKEND", "mock")
    if mode not in {"mock", "real"}:
        raise ValueError("KPMG_GRAPH_BACKEND must be mock or real")
    module = importlib.import_module("mock.mock_retrieval_tools" if mode == "mock" else "graphrag.retrieve")
    chunks = getattr(module, tool)(query=query, filters=filters, top_k=top_k, trace_id=trace_id)
    return [_to_evidence(c) for c in chunks]


def graph_search(**kwargs):
    return retrieve_graph(**kwargs, tool="graph_search")


def structured_search(**kwargs):
    return retrieve_graph(**kwargs, tool="structured_search")


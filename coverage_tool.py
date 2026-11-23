def precheck_coverage(query: str) -> dict:
    """Run the RAG coverage pre-check for an Agent query."""
    from rag.coverage import precheck_question

    return precheck_question(query)

"""Prime the same process-local Chroma and coverage objects used by retrieval."""

import json
import logging
import os
from pathlib import Path
from time import perf_counter

log = logging.getLogger(__name__)


def warm_chroma():
    if (os.getenv("KPMG_CHROMA_WARMUP", "1") != "1" or os.getenv("KPMG_RAG_BACKEND") != "real"
            or os.getenv("RAG_BACKEND", "").lower() != "chroma" or not os.getenv("RAG_CHROMA_DIR")):
        return {"status": "skipped", "duration_ms": 0}
    start = perf_counter()
    try:
        meta = json.loads((Path(os.environ["RAG_CHROMA_DIR"]) / "meta.json").read_text())
        if not meta.get("embedder", "").startswith("st:"):
            return {"status": "skipped", "reason": "local embedding model required", "duration_ms": 0}
        from rag.coverage import default_index
        from rag.retrieve import _default_retriever

        retriever = _default_retriever()
        retriever.embedder.encode(["SEC filing retrieval warm-up"], is_query=True)
        if os.getenv("KPMG_COVERAGE_PRECHECK") == "1":
            default_index()
    except Exception as exc:
        log.warning("Chroma startup warm-up failed (%s); lazy retrieval remains available", type(exc).__name__)
        return {"status": "failed", "duration_ms": round((perf_counter() - start) * 1000, 2)}
    return {"status": "ready", "duration_ms": round((perf_counter() - start) * 1000, 2)}

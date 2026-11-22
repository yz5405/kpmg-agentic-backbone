# kpmg-agentic-backbone
Agentic workflow orchestration for KPMG Financial Document Q&amp;A

## v0.4 integration review

The existing RAG-first workflow remains the default. Set
`KPMG_GRAPHRAG_ENABLED=1` and `KPMG_TOOL_SELECTION=auto` to enable capability-based
selection. Vector handles SEC narrative retrieval, Structured handles supported
single-company financial lookups, and Graph handles explicit claim keyword
search. Company rankings and traversal questions abstain pending a complete
coverage check and a suitable execution tool.

### Local environment

1. Install `requirements.txt` and `requirements-answer.txt` in a virtual environment.
   Install the RAG team's requirements plus `neo4j`, `duckdb`, and `pandas` in that environment.
2. Add the RAG `final_v2` checkout and GraphRAG checkout to `PYTHONPATH`.
3. Set `KPMG_RAG_BACKEND=real`, `RAG_BACKEND=chroma`, and
   `RAG_CHROMA_DIR` to the extracted frozen index. Set `MSFT_FACT_DB_PATH` to the
   confirmed local corpus. Set `RAG_LOG_DIR` to a private local directory.
4. Use the approved local Neo4j configuration through `NEO4J_URI`,
   `NEO4J_USERNAME`, `NEO4J_DATABASE`, and `NEO4J_PASSWORD`. The driver must trust
   the CA chain. Keep `CYPHER_ARM_ENABLED` disabled for this integration.
5. For authorized live model tests, supply `OPENAI_API_KEY` locally and configure
   `KPMG_QUERY_LLM_ENABLED=1`, `KPMG_QUERY_LLM_MODEL`, `KPMG_ANSWER_ENABLED=1`,
   `KPMG_ANSWER_MODEL` and the approved `OPENAI_BASE_URL` if required. Set both
   LLM flags to zero for reproducible local retrieval checks.
6. Start `python -m uvicorn api.main:app --host 127.0.0.1 --port 8765`.

To attach Financial Explorer, download the UI team's v2 HTML from commit
`48a9336`, then build a local copy with
`python scripts/build_financial_explorer.py path/to/prototype.html path/to/live.html`.
Set `KPMG_EXPLORER_HTML` to the full path of the generated HTML, restart FastAPI,
and open `http://127.0.0.1:8765/explorer`. The page calls the same-origin
`/query` endpoint and renders validated SEC links. Keep local indexes and
credentials outside Git.

### Validation commands

| Layer | Command | Expected result |
| --- | --- | --- |
| Unit and API policy | `python -m pytest -q` | Regression and policy tests pass |
| Real DuckDB | `python scripts/check_structured_filters.py` | Scoped rows, no wrong-period overlap, multi-company results, missing fiscal year rejected |
| Eval extraction | `PYTHONPATH=. python scripts/run_extraction.py INPUT.jsonl OUTPUT_DIR --mode rules` | 427 separate records for the supplied Eval dataset. Use `--mode llm` only for an approved live run |
| Local retrieval traces | `python scripts/run_local_traces.py OUTPUT.jsonl` | 20 sanitized records comparing two top-k values over the same ten questions |

See [the integration review](docs/v04-integration-review.md) for acceptance boundaries.

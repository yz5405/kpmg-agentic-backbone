# Joint RAG integration verification

Set `KPMG_RAG_BACKEND=real`, `KPMG_COVERAGE_PRECHECK=1`, `RAG_BACKEND=chroma` and `RAG_CHROMA_DIR` to the absolute path of the team-approved frozen index. Put the joint-compatible RAG checkout on `PYTHONPATH`. Set the approved LLM configuration locally if available. Use the existing API or run the checklist against the local app:

```sh
PYTHONPATH=".:$PYTHONPATH" python scripts/run_joint_e2e.py CHECKLIST.md OUTPUT_DIR
```

Keep the checklist and generated results outside Git. The runner resolves the checklist's three explicitly referential rows without changing the others. Case 14 runs in a fresh process, and case 15 repeats case 8 with GraphRAG enabled.

The integration combines Agent company recognition with the RAG coverage extractor, uses rule-derived periods, and passes verified company–accession pairs to `retrieve_multi`. `joint_trace` exposes the precheck, actual subqueries, timings, and returned and accepted counts. Existing response fields remain available. Unresolved or absent coverage produces a direct explanation, and a missing company produces clarification. Unsupported calculations and Exhibit 21 counts remain explicit limitations.

The benchmark results distinguish approved live answers from retrieval-only outcomes. A missing persistence marker or incomplete persisted HNSW graph prevents formal sign-off even when a single fresh-process order comparison agrees.

## Review follow-up

The API exposes `calculation_status` and `calculation_reason` separately from accepted evidence. Unsupported calculations retain validated revenue inputs and skip answer generation. `retrieval_citations` contains supporting material surfaced by retrieval. `citations` contains references actually used by a generated answer on the joint path.

With real Chroma configured, FastAPI primes the local sentence-transformer and coverage manifest during startup. To disable the warm-up, set `KPMG_CHROMA_WARMUP=0`. The service continues with lazy retrieval if warm-up fails. Compare independent processes with:

```sh
PYTHONPATH=".:$PYTHONPATH" python scripts/check_chroma_warmup.py OUTPUT.json 'What was Microsoft's total revenue for the three months ended March 31, 2026?'
```

For the follow-up model validation, first load the approved configuration locally. Then run:

```sh
PYTHONPATH=".:$PYTHONPATH" python scripts/run_joint_e2e.py CHECKLIST.md OUTPUT_DIR --cases 2 4 5 8 --live-llm
```

Case 4 must remain blocked without a validated calculator even with live answer generation enabled. Use a separate output directory per run.

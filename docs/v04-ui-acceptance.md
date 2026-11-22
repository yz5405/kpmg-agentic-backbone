# Financial Explorer v2 acceptance

The local browser smoke test used a running FastAPI service with real retrieval from frozen Chroma and DuckDB. A Microsoft quarterly revenue request returned `SUCCESS` and displayed a clickable SEC filing link. A cross-company comparison outside the supported calculation scope returned `NO_EVIDENCE` and displayed the limitation.

LLM answer generation was disabled. Live model output in the browser is pending an approved LLM configuration. These results were recorded in the historical browser output and review notes. A standalone browser report, screenshot, or raw trace was not retained for this run.

## Reproduce

Use the [Financial Explorer build and API setup](../README.md#local-environment), open `/explorer` from the local Agent service, and submit a supported FY2026 Q3 revenue lookup followed by a cross-company comparison. Verify the SEC link on the successful lookup and the visible abstention on the unsupported comparison.

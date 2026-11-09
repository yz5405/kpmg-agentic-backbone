# Financial Explorer demo — Drive snapshot

Original five files from the Drive `11.5` folder, uploaded without source changes.

Source: https://drive.google.com/drive/folders/1fe2qzx5PiHzjgRoSlWCnRxRzcd8QlNKb

- `01_UI_explorer.html`: Financial Explorer interface.
- `02_API_main.py`: FastAPI endpoints.
- `03_GraphRAG_graphrag_adapter.py`: GraphRAG adapter.
- `04_Workflow_orchestrator.py`: planning, retrieval, evidence review, and answers.
- `05_Integration_integration.py`: integration entry point.

## Integration status

This folder preserves the source snapshot; the numbered filenames are not installed Python module paths. The Python files depend on the project's `agent` package and additional retrieval/generation modules. The API also refers to `demo.html` and `explorer.html` next to its installed module. These files must be mapped to their intended package locations and missing dependencies supplied before running the full demo. The UI uses an API for answers; opening the HTML alone does not start a backend. Charts are illustrative, as labelled in the UI.


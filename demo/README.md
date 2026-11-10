# kpmg-agentic-backbone Demo
Agentic workflow orchestration for KPMG Financial Document Q&A.

[中文说明](README_CN.md)

## Run the demo

**Backend entry: `app/main.py`. Web page: `app/static/index.html`.**
Start the backend with the commands below, then open **http://localhost:8000** in your browser.
Double-clicking the HTML file only previews the interface; it does not start the question-answering service. Do not run `app/main.py` directly.

Requires Python 3.12. Open a terminal in this package's root directory (the folder containing `requirements.txt` and `Dockerfile`). If uploaded under `demo/runnable/`, enter that directory first.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### macOS / Linux

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Keep the terminal open while using the demo. Press Ctrl+C to stop it.
After startup, open http://localhost:8000 and try:
- `What was Microsoft total revenue for Q3 FY2026?`
- `What was Microsoft operating income for Q3 FY2026?`

## What this version demonstrates

The browser sends questions to `POST /query`. The Agent plans a retrieval route, retrieves bundled sample evidence, checks citation metadata, and returns evidence excerpts and citations.

This version uses **mock RAG/GraphRAG retrieval and offline, extractive answers**. No API key is required. It does not connect to live SEC data, a production graph database, or an LLM. The small sample corpus is centered on Microsoft Q3 FY2026; other companies or periods may return no evidence. Dashboard charts are illustrative and are not calculated from retrieved answers.

## Project structure

| Path | Purpose |
| --- | --- |
| `app/main.py` | FastAPI application entry point; serves the page and question API |
| `app/static/index.html` | Active demo interface |
| `agent/` | Query parsing, workflow orchestration and retrieval adapters |
| `graphrag/` and `mock/` | GraphRAG contract and sample retrieval implementation |
| `demo/` | Original numbered source files retained for reference; not the runnable entry |
| `tests/` | API and workflow integration tests |
| `requirements.txt` | Runtime dependencies |
| `Dockerfile` and `render.yaml` | Deployment configuration |

This package includes copies of some existing repository code. Upload the **whole package**, preserving its folders, under `demo/runnable/` to avoid overwriting the repository's existing root-level modules.

## Docker and Render

Run these commands from this package's root:

```sh
docker build -t financial-explorer .
docker run --rm -p 8000:8000 financial-explorer
```

Then open http://localhost:8000.

For a Render Docker web service, if this package is at `demo/runnable/`, set Docker context to `demo/runnable` and Dockerfile path to `demo/runnable/Dockerfile`. If it is the repository root, use `.` and `Dockerfile`. The container uses Render's `PORT` environment variable. Serve the UI and API together; a static HTML host alone cannot run this backend. No public deployment URL is included in this package.

## Verification

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Use the virtual environment's Python as in the startup commands. Four integration test groups passed on Windows / Python 3.12, covering page delivery, RAG and graph routing, trace IDs, validation, clarification and no-evidence responses. Browser visual QA and Docker execution were not performed.

## Sources

- [Agent repository](https://github.com/yz5405/kpmg-agentic-backbone): original workflow and demo.
- [GraphRAG repository](https://github.com/ZiyiClaudiaWang/KPMG-GraphRAG): contract and mock retrieval tools.

Keep `KPMG_MODEL_BACKEND=offline` for this package. Real retrieval and model-based answers require additional team packages, data, backend configuration and credentials.

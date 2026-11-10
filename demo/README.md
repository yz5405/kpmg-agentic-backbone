# KPMG Financial Explorer Demo

[中文说明](README_CN.md)

## Try online

**[Open the demo](https://kpmg-financial-explorer.onrender.com)** — no installation or deployment required.

Enter a question, for example:
- `What was Microsoft total revenue for Q3 FY2026?`
- `What was Microsoft operating income for Q3 FY2026?`

## Demo scope

- Uses bundled RAG/GraphRAG sample data, mainly Microsoft Q3 FY2026.
- Returns evidence excerpts and source citations; no LLM-generated answers.
- Charts use illustrative data. Live retrieval services are not connected.
- Other companies or periods may return no evidence.

## Run locally (developers)

Download and extract `github-demo.zip`. Open a terminal in the extracted folder containing `requirements.txt`. Requires Python 3.12.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

macOS / Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **http://localhost:8000**. Keep the terminal running; press Ctrl+C to stop.

Backend entry: `app/main.py`. Active page: `app/static/index.html`. Opening an HTML file directly only previews the interface; it does not start the backend. The numbered files in `demo/` are reference copies.

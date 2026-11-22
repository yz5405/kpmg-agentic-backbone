# KPMG 财务问答 Demo

[English](README.md)

## 在线试用

**[打开 Demo](https://kpmg-financial-explorer.onrender.com)**，无需安装或自行部署。

打开后输入问题，例如：
- `What was Microsoft total revenue for Q3 FY2026?`
- `What was Microsoft operating income for Q3 FY2026?`

## 演示范围

- 使用内置 RAG/GraphRAG 示例数据，主要覆盖微软 Q3 FY2026。
- 返回证据摘录及来源引用，不使用大语言模型生成答案。
- 图表为示意数据，尚未接入真实检索服务。
- 其他公司或期间可能返回“无证据”。

## 本地运行（开发者）

下载并解压 `github-demo.zip`，在包含 `requirements.txt` 的解压目录打开终端。需要 Python 3.12。

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

macOS / Linux：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

浏览器打开 **http://localhost:8000**。使用时保持终端运行，按 Ctrl+C 停止。

后端入口：`app/main.py`；实际网页：`app/static/index.html`。直接打开 HTML 只能预览界面，不能启动后端。`demo/` 中的编号文件为参考副本。

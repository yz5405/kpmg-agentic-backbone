# kpmg-agentic-backbone Demo
面向 KPMG 财务文档问答的 Agent 工作流演示。

[English README](README.md)

## 如何运行 demo

**后端入口：`app/main.py`。网页文件：`app/static/index.html`。**
先按下面的命令启动后端，再在浏览器打开 **http://localhost:8000**，即可使用 demo。
双击 HTML 文件只能预览界面，不能启动问答服务；也不需要直接双击或执行 `app/main.py`。

需要 Python 3.12。在本项目根目录打开终端，即同时包含 `requirements.txt` 和 `Dockerfile` 的文件夹。如果上传在仓库的 `demo/runnable/` 下，请先进入该目录。

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

使用时保持终端运行；按 Ctrl+C 停止服务。
启动成功后，在浏览器打开 http://localhost:8000，可以输入：
- `What was Microsoft total revenue for Q3 FY2026?`
- `What was Microsoft operating income for Q3 FY2026?`

## 当前版本能演示什么

网页通过 `POST /query` 发送问题。Agent 选择检索路线，检索内置示例证据，检查引用信息，并返回证据摘录及来源引用。

当前使用 **RAG/GraphRAG 模拟检索和离线证据摘录**，不需要 API Key。尚未连接实时 SEC 数据、生产图数据库或大语言模型。示例语料主要围绕微软 Q3 FY2026，其他公司或期间可能返回“无证据”。仪表盘图表为示意数据，不是根据检索答案生成的财务图表。

## 文件说明

| 路径 | 用途 |
| --- | --- |
| `app/main.py` | FastAPI 后端入口，提供网页和问答接口 |
| `app/static/index.html` | 实际运行的 demo 网页 |
| `agent/` | 问题解析、工作流编排及检索适配 |
| `graphrag/`、`mock/` | GraphRAG 接口契约和模拟检索实现 |
| `demo/` | 保留的原始编号文件，供参考，不是运行入口 |
| `tests/` | 接口和工作流集成测试 |
| `requirements.txt` | 运行依赖 |
| `Dockerfile`、`render.yaml` | 部署配置 |

本项目包含部分原仓库代码的副本。上传时应将**整个项目的所有文件和文件夹**放到 `demo/runnable/`，保留目录结构，避免覆盖仓库根目录原有模块。

## Docker 与 Render 部署

在本项目根目录执行：

```sh
docker build -t financial-explorer .
docker run --rm -p 8000:8000 financial-explorer
```

然后打开 http://localhost:8000。

在 Render 创建 Docker Web Service 时，如果项目位于 `demo/runnable/`，Docker context 设置为 `demo/runnable`，Dockerfile path 设置为 `demo/runnable/Dockerfile`；如果项目就在仓库根目录，则分别使用 `.` 和 `Dockerfile`。容器会使用 Render 提供的 `PORT` 环境变量。网页和 API 应由同一个服务提供；单独托管静态 HTML 无法运行 Python 后端。本压缩包尚不包含已部署的公开访问链接。

## 测试与验证

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

请像启动步骤一样使用虚拟环境中的 Python。已在 Windows / Python 3.12 下通过 4 组集成测试，覆盖网页加载、RAG 和图检索路由、trace ID、请求校验、澄清及无证据处理。尚未执行浏览器视觉检查和 Docker 容器验证。

## 代码来源

- [Agent 仓库](https://github.com/yz5405/kpmg-agentic-backbone)：原工作流及 demo。
- [GraphRAG 仓库](https://github.com/ZiyiClaudiaWang/KPMG-GraphRAG)：接口契约与模拟检索工具。

本项目请保持 `KPMG_MODEL_BACKEND=offline`。接入真实检索及模型生成答案，需要额外的团队代码包、数据、后端配置和凭据。

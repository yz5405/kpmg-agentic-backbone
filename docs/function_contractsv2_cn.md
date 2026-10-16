
# Agentic Backbone — Function Contracts v0.2 中文版

**项目：** Columbia QMSS × KPMG Financial Document Q&A  
**更新日期：** 2026年10月15日  
**MVP 截止日期：** 2026年10月22日  
**目标框架：** LangGraph + Python  
**未来方向：** Hierarchical Multi-Agent Architecture（分层多智能体架构）  
**当前状态：** 已测试 LangChain Mock Workflow；LangGraph 迁移和真实 RAG 集成尚未完成。

---

## 1. Purpose and Development Scope — 文档目标与开发范围

这份文档定义 Agentic Backbone Team 五个模块的 Function Contracts（函数接口规范）。

Function Contract 的作用是明确：

- 每个组员需要实现什么函数。
- 函数接受什么 Input（输入）。
- 函数返回什么 Output（输出）。
- 应该如何处理 Error（错误）。
- 需要通过哪些 Acceptance Tests（验收测试）。
- 如何与 LangGraph Workflow 集成。

根据 KPMG 10月15日的反馈，我们决定向 LangGraph-based Architecture 转型，并为未来的 Hierarchical Multi-Agent System 做准备。

### October 22 MVP 包含

1. Query Understanding（问题理解）
2. RAG Tool Integration（检索工具集成）
3. Conditional Routing（条件路由）
4. Shared State and Execution Logging（共享状态与执行日志）
5. Automated Testing（自动化测试）
6. LangGraph Workflow Orchestration（工作流编排）

MVP 的基本目标是完成一个从 Financial Question 到 Evidence Output 的完整流程。

### October 22 暂时不要求

- 多个自主运行的 LLM Agents
- LLM Answer Generation
- 真实 GraphRAG Retrieval
- SQL Tool Integration
- Persistent Conversation Memory
- 正式部署的 Frontend / Backend

### Development Rules — 开发规则

1. 每位组员负责一个模块及其 Public Functions（公开函数）。
2. Team Leads 负责整个 LangGraph `StateGraph`。
3. 每个模块必须能够独立测试。
4. 模块函数不应该直接依赖整个 Graph。
5. 组员可以根据需要使用 LangGraph。
6. Shared Contracts 的任何修改都需要 Team Leads 确认。
7. 不得将 API Keys、Credentials 或敏感信息上传至 GitHub。
8. LangGraph 迁移期间应尽量保留现有功能。

---

## 2. LangGraph Integration Principles — LangGraph 集成原则

LangGraph 负责协调和执行各个独立的 Python Functions。

主 Workflow 将使用：

- **StateGraph**：定义整体工作流。
- **Nodes**：执行具体任务的节点。
- **Edges**：节点之间的连接。
- **Conditional Edges**：根据条件选择执行路径。
- **Shared State**：在节点之间传递信息。
- **Execution Logging**：记录执行过程。

### Core Design Principle — 核心原则

**模块功能的开发与整个 Graph 的编排是两个不同的职责。**

- **组员：** 实现自己的 Python Functions。
- **Team Leads：** 将这些 Functions 封装为 LangGraph Nodes，并连接到 Main Workflow。

例如：

```python
def understand_query(query: str) -> dict:
    # Member 1 负责实现
    ...

def query_node(state: dict) -> dict:
    # Team Leads 负责 LangGraph Wrapper
    filters = understand_query(state["query"])
    return {"filters": filters}
```

这里：

- `understand_query()` 负责真正解析用户问题。
- `query_node()` 负责让这个函数能够在 LangGraph 中执行。

这样的结构有利于独立测试、维护和未来复用。

### LangGraph Node Contract — 节点接口规范

主 Graph 使用 Dictionary-based State。

每个 Node 应当：

1. 接收当前 Graph State。
2. 执行自己的任务。
3. 只返回自己负责更新的 State Fields。
4. 不随意修改其他模块的字段。
5. 支持 Workflow 记录错误和执行事件。

最终 Node Wrappers 由 Team Leads 在 `agent/workflow.py` 中统一实现。

---

## 3. Shared State Contract — 共享状态接口

**负责人：**
- Team Leads：最终 State Schema 设计
- Lingfei Zhang：Logging 和 State Support

**文件：** `agent/state.py`

目前 v0.1 使用 Python `dataclass` 定义 `AgentState`。

在 v0.2 中，主 LangGraph Workflow 将采用兼容 `TypedDict` 的 State Schema。

**注意：这是计划中的迁移，当前 GitHub 代码尚未完成切换。**

### Target LangGraph State — 目标状态结构

```python
from typing import Any, TypedDict

class AgentGraphState(TypedDict):
    query: str
    filters: dict[str, Any]
    top_k: int
    evidence: list[dict[str, Any]]
    status: str
    error: str | None
    logs: list[str]
```

### Required Fields — 必须保留的字段

| Field | Type | 中文含义 |
|---|---|---|
| `query` | str | 用户原始金融问题 |
| `filters` | dict | 解析出的金融筛选条件 |
| `top_k` | int | Retriever 最多返回的结果数量 |
| `evidence` | list[dict] | 检索得到的证据及来源信息 |
| `status` | str | Workflow 当前或最终执行状态 |
| `error` | str / None | 错误信息 |
| `logs` | list[str] | 按执行顺序保存的日志 |

### Status Constants — 状态常量

- `PENDING`
- `SUCCESS`
- `NO_EVIDENCE`
- `ERROR`

### State Initialization — 状态初始化

Team Leads 将维护以下初始化逻辑：

```python
def create_initial_state(
    query: str,
    top_k: int = 10
) -> dict:
    return {
        "query": query,
        "filters": {},
        "top_k": top_k,
        "evidence": [],
        "status": "PENDING",
        "error": None,
        "logs": []
    }
```

### Migration Rules — 迁移规则

1. 保留原来的七个核心字段。
2. 组员不得自行重新设计 State Schema。
3. 旧版 Dataclass 可以暂时保留，保证 Backward Compatibility（向后兼容）。
4. Team Leads 决定主 Workflow 什么时候正式切换到 `AgentGraphState`。
5. 同一个 Node 中不要混用 Dataclass Attribute Access 和 Dictionary Access。
6. 每次测试都需要使用全新的 State。
7. 不得在 State 或 Logs 中存储 Credentials。

### Logging State Updates — 日志状态更新

LangGraph 的 Nodes 应通过显式返回 State Updates 更新状态，而不是依赖直接修改传入对象。

对于初版 MVP：

- `logs` 使用普通的 List。
- 每个 Node Wrapper 在新增日志时，返回更新后的完整日志列表。

例如：

```python
return {
    "logs": state["logs"] + ["[INFO] Query parsing completed"]
}
```

未来如果需要多个 Agents 并行执行，可以进一步使用 Reducers 处理并发状态更新。

---

## 4. Module 1 — Query Understanding

**负责人：** Jixuan Liu  
**文件：** `agent/query_parser.py`

### Function Signature — 函数接口

```python
def understand_query(query: str) -> dict:
    """Extract financial filters from a user question."""
```

### Input — 输入

- `query`：用户提出的原始 Financial Question。

### Output — 输出

必须返回包含以下三个 Key 的 Dictionary：

```python
{
    "ticker": str | None,
    "fiscal_year": int | None,
    "fiscal_period": str | None
}
```

这里展示的是字段类型规范，不是可直接运行的返回值。

### Example — 示例

**Input:**

```text
What was Microsoft's revenue in Q3 FY2026?
```

**Expected Output:**

```python
{
    "ticker": "MSFT",
    "fiscal_year": 2026,
    "fiscal_period": "Q3"
}
```

### Requirements — 开发要求

1. Oct 22 MVP 使用 Rule-based Parsing（规则解析）。
2. 识别支持范围内的公司名称和 Ticker。
3. 提取 Fiscal Year。
4. 提取 Fiscal Quarter。
5. 无法识别的字段返回 `None`。
6. 始终返回三个必要字段。
7. 不负责调用 Retriever。
8. 不调用 LLM API。
9. 不直接修改 Shared State。
10. 对空字符串或无效输入抛出 `ValueError`。

### LangGraph Integration

Team Leads 将实现类似下面的 Node：

```python
def query_node(state: AgentGraphState) -> dict:
    filters = understand_query(state["query"])

    return {
        "filters": filters
    }
```

Jixuan 不需要自己开发单独的 `StateGraph`。

### Acceptance Tests — 验收测试

**Case 1：完整 Filters**

Input:

```text
Microsoft Q3 FY2026
```

Expected:

```python
{
    "ticker": "MSFT",
    "fiscal_year": 2026,
    "fiscal_period": "Q3"
}
```

**Case 2：部分 Filters**

Input:

```text
Microsoft FY2025
```

Expected:

```python
{
    "ticker": "MSFT",
    "fiscal_year": 2025,
    "fiscal_period": None
}
```

**Case 3：无法识别**

Input:

```text
Revenue performance
```

Expected:

```python
{
    "ticker": None,
    "fiscal_year": None,
    "fiscal_period": None
}
```

**Case 4：无效输入**

空字符串或非字符串输入必须抛出 `ValueError`。

### Ownership Boundary — 职责边界

- **Jixuan：** 负责 Financial Filter Extraction。
- **Team Leads：** 负责 LangGraph Node Wrapper。

---

## 5. Module 2 — RAG Tool Integration

**负责人：** Jiahui Yang  
**文件：** `agent/tools/rag_tool.py`

### Function Signature

```python
def retrieve_evidence(
    query: str,
    filters: dict | None = None,
    top_k: int = 10
) -> list[dict]:
    """Retrieve and normalize evidence from the RAG tool."""
```

### Upstream Retrieval Contract — 上游检索接口

RAG Team 提供的接口：

```python
retrieve(
    query: str,
    filters: dict | None = None,
    top_k: int = 10
) -> list[RetrievedChunk]
```

RAG Team 在会议中报告：

- Retrieval Contract 已经合并。
- Retriever 已被封装为 LangChain Tool。

但我们仍然需要在自己的环境中验证其真实调用方式和 Output。

### Input — 输入

- `query`：金融问题。
- `filters`：解析出的金融筛选条件。
- `top_k`：最多返回多少个 Retrieval Results。

### Output — 输出

返回统一格式的 Evidence Dictionaries。

例如：

```python
[
    {
        "text": "Example filing evidence...",
        "metadata": {
            "ticker": "MSFT",
            "fiscal_year": 2026,
            "fiscal_period": "Q3",
            "source": "10-Q"
        }
    }
]
```

这里是我们 Agent Team 的 Internal Normalized Format，并非已经确认的 RAG 原始输出字段全集。

### Requirements — 开发要求

1. 集成 RAG Team 已有的 Retriever。
2. 保留约定的 Public Function Signature。
3. 不重新开发 Retrieval Engine。
4. 正确传入 Financial Metadata Filters。
5. 保留 Source IDs 和可用的 Citation Metadata。
6. 统一输出 Evidence Dictionaries。
7. 没有结果时返回空列表 `[]`。
8. `top_k <= 0` 时抛出 `ValueError`。
9. 对非预期的 Retrieval Exceptions 进行异常传递。
10. 不负责 LLM Answer Generation。
11. 不直接修改 Shared Graph State。
12. 保留 Mock Retriever 或测试 Fixture，方便进行可重复测试。

### LangGraph Integration

Team Leads 负责将 Adapter 封装为 LangGraph Node：

```python
def retrieval_node(state: AgentGraphState) -> dict:
    evidence = retrieve_evidence(
        query=state["query"],
        filters=state["filters"],
        top_k=state["top_k"]
    )

    return {
        "evidence": evidence
    }
```

### External Integration Checklist

需要和 RAG Team 确认：

1. Python Import Path（导入路径）
2. Package Dependencies（依赖包）
3. Input Parameters（输入参数）
4. `RetrievedChunk` Fields / Types（字段和类型）
5. Citation / Provenance Metadata（引用和来源信息）
6. Company / Fiscal Period Filters（支持的筛选条件）
7. Empty Result Behavior（空结果行为）
8. Error / Timeout Behavior（异常与超时行为）

### Acceptance Tests

**Case 1 — Successful Retrieval**

- 返回非空 Evidence List。
- 每个 Evidence Item 包含 Text 和 Metadata。
- 保留来源信息。

**Case 2 — No Evidence**

- Mock Retriever 返回 `[]`。
- Adapter 也返回 `[]`。

**Case 3 — Invalid Parameter**

- 输入 `top_k = 0`。
- 预期抛出 `ValueError`。

**Case 4 — Upstream Failure**

- Mock Retriever 抛出异常。
- Adapter 将异常向上传递。

**Case 5 — Metadata Preservation**

- Source IDs 和可用 Metadata 在格式转换后仍然可以读取。

### Ownership Boundary

- **Jiahui：** RAG Adapter 和 Evidence Normalization。
- **Team Leads：** LangGraph Retrieval Node 和 Orchestration。
- **RAG Team：** Retriever Engine 本身。

---

## 6. Module 3 — Conditional Routing

**负责人：** Lidan Yu  
**文件：** `agent/routing.py`

### Existing Function Signature — 原有函数

```python
from agent.state import AgentState

def route_result(state: AgentState) -> AgentState:
    """Determine workflow status from evidence and errors."""
```

### v0.2 新增函数

为支持 LangGraph，同时保留原有函数的兼容性，Lidan 需要新增：

```python
def determine_status(
    evidence: list[dict],
    error: str | None
) -> str:
    """Return SUCCESS, NO_EVIDENCE, or ERROR."""
```

两个函数的区别：

- `route_result()`：接收旧版 `AgentState`，修改其 Status。
- `determine_status()`：根据 Evidence 和 Error，直接返回 Status String。

第二个函数更方便在 LangGraph 中调用和测试。

### Routing Rules — 路由规则

1. 如果 `error is not None`，返回 `ERROR`。
2. 否则，如果 Evidence 非空，返回 `SUCCESS`。
3. 否则，返回 `NO_EVIDENCE`。

**Error 的优先级高于 Evidence。**

### LangGraph Integration

Team Leads 将实现：

```python
def routing_node(state: AgentGraphState) -> dict:
    status = determine_status(
        evidence=state["evidence"],
        error=state["error"]
    )

    return {
        "status": status
    }
```

Conditional Edges 再通过以下函数选择流程分支：

```python
def select_outcome(state: AgentGraphState) -> str:
    return state["status"]
```

具体的 `add_conditional_edges()` 连接由 Team Leads 统一设计。

### Requirements

1. 保留原来的 Routing Behavior。
2. 新增可复用的 Status Decision Function。
3. 不负责调用 RAG、GraphRAG 或 SQL。
4. 不调用 LLM API。
5. 不修改 Evidence。
6. 不独立搭建 Main Graph。
7. 只返回规定的 Status Values。

### Acceptance Tests

| Evidence | Error | Expected Status |
|---|---|---|
| 非空 | None | SUCCESS |
| 空 | None | NO_EVIDENCE |
| 空 | Error Message | ERROR |
| 非空 | Error Message | ERROR |

### Future Multi-Agent Routing

未来可以逐步支持：

- Document Retrieval
- Graph Retrieval
- Structured-data Retrieval
- Evidence Verification
- Answer Synthesis

但这些不属于 Oct 22 必须实现的 `determine_status()` 功能。

### Ownership Boundary

- **Lidan：** Routing Rules 和 Decision Functions。
- **Team Leads：** Conditional Edges 和完整 StateGraph。

---

## 7. Module 4 — State Management & Execution Logging

**负责人：** Lingfei Zhang  
**文件：**

- `agent/state.py`
- `agent/logging_utils.py`

### Responsibilities — 主要职责

1. 在迁移期间维护已有 State Definitions。
2. 完成 Execution Logging。
3. 支持 LangGraph-compatible Logging。
4. 确保 Logs 体现真实执行顺序。
5. 避免记录敏感信息。

### Existing Function Contract — 原有函数

```python
from agent.state import AgentState

def log_event(
    state: AgentState,
    message: str,
    level: str = "INFO"
) -> None:
    """Append an execution log to the existing AgentState."""
```

这个函数需要继续兼容已有测试。

### New LangGraph-Compatible Logging Helper — 新增函数

```python
def format_log_event(
    message: str,
    level: str = "INFO"
) -> str:
    """Return a formatted log entry."""
```

示例：

```python
format_log_event("RAG retrieval started")

# "[INFO] RAG retrieval started"
```

两个函数的区别：

- `log_event()`：向旧版 `AgentState.logs` 添加日志。
- `format_log_event()`：只返回格式化后的 Log String。

Team Leads 可以直接在 LangGraph Node 中使用第二个函数。

例如：

```python
def append_graph_log(
    state: AgentGraphState,
    message: str,
    level: str = "INFO"
) -> dict:
    entry = format_log_event(message, level)

    return {
        "logs": state["logs"] + [entry]
    }
```

### Supported Log Levels

- INFO
- WARNING
- ERROR

### Formatting Rules

1. 格式为 `[LEVEL] message`。
2. 小写 Level 转换为大写。
3. 不支持的 Level 抛出 `ValueError`。
4. 按照实际执行顺序保存 Logs。
5. 不记录 API Keys、Passwords 或其他敏感信息。

### Tool Calling Sequence — 工具调用记录

KPMG 特别强调 LangGraph 应支持 Tool Calling Sequence Logging。

MVP 至少记录：

- Workflow Start
- Query Parsing Start / Completion
- Retrieval Tool Start / Completion
- Retrieval Failure
- Routing Result
- Workflow Completion

例如：

```text
[INFO] Workflow started
[INFO] Query parsing started
[INFO] Query parsing completed
[INFO] RAG retrieval started
[INFO] RAG retrieval completed
[INFO] Workflow status: SUCCESS
```

这些内容必须来自实际执行过程，不能仅仅为了 Demo 硬编码输出。

### Requirements

1. 保留旧版 Logging Interface。
2. 新增 `format_log_event()`。
3. 不独立重新设计 `AgentGraphState`。
4. 不实现 Persistent Session Memory。
5. 不独立修改 Main LangGraph Graph。
6. 保证日志可以进行 Deterministic Unit Testing。
7. State Changes 必须先与 Team Leads 协调。

### Acceptance Tests

**Case 1 — INFO Formatting**

```python
assert format_log_event("Workflow started") == \
    "[INFO] Workflow started"
```

**Case 2 — ERROR Formatting**

```python
assert format_log_event(
    "Retrieval failed", "ERROR"
) == "[ERROR] Retrieval failed"
```

**Case 3 — Lowercase Level**

```python
assert format_log_event(
    "No evidence", "warning"
) == "[WARNING] No evidence"
```

**Case 4 — Invalid Level**

不支持的 Level 抛出 `ValueError`。

**Case 5 — State Isolation**

不同 Workflow Executions 的 Logs 不能互相影响。

**Case 6 — Execution Order**

日志顺序必须与实际执行顺序一致。

### Ownership Boundary

- **Lingfei：** Logging Utilities 和 State Support。
- **Team Leads：** 最终 LangGraph State Schema 和 Workflow Logging Integration。

---

## 8. Module 5 — Testing & Quality Assurance

**负责人：** Yichen Liu  
**文件夹：** `tests/`

### Objective — 目标

验证各模块是否遵守 Function Contracts，以及整个 Workflow 是否能够运行。

测试范围包括：

- 原有 Python Modules
- 新的 LangGraph Workflow

### Testing Framework

使用 `pytest`。

在 Repository Root 运行：

```bash
python -m pytest tests/ -v
```

### Required Test Files

- `tests/test_query_parser.py`
- `tests/test_rag_tool.py`
- `tests/test_routing.py`
- `tests/test_logging.py`
- `tests/test_workflow.py`

保留已有的 `tests/test_skeleton.py`。

### Module Tests — 单元测试

**Query Understanding**

- Complete Filters
- Partial Filters
- Unknown Filters
- Invalid Input

**RAG Adapter**

- Successful Retrieval
- Empty Result
- Invalid `top_k`
- Retriever Exceptions
- Metadata Preservation

**Routing**

- SUCCESS
- NO_EVIDENCE
- ERROR
- Error Priority

**Logging**

- INFO Formatting
- ERROR Formatting
- Level Normalization
- Invalid Levels
- Execution Order
- State Isolation

### LangGraph Integration Tests — 集成测试

Yichen 与 Team Leads 一起检查：

1. Graph Entry Point 是否正确。
2. Node Execution Sequence 是否符合预期。
3. Nodes 之间的 State Updates 是否正确。
4. Conditional Routing 是否正确。
5. Final Output Structure 是否符合要求。
6. Error Handling 是否正常。
7. Execution Logs 是否正确。
8. 不同运行之间是否发生 State Contamination（状态污染）。

### Minimum End-to-End Scenarios

**Scenario 1 — SUCCESS**

Input:

```text
Microsoft Q3 FY2026
```

Expected:

- Financial Filters 正确提取。
- 返回 Mock Evidence。
- Source Metadata 得到保留。
- `status = SUCCESS`。
- 产生 Execution Logs。

**Scenario 2 — NO_EVIDENCE**

使用返回空列表的确定性 Mock Fixture。

Expected:

- `evidence = []`
- `status = NO_EVIDENCE`
- Workflow 正常结束，不发生 Crash。

**Scenario 3 — ERROR**

Input:

```text
top_k = 0
```

Expected:

- Retrieval Parameter Validation 失败。
- Error Message 被记录。
- `status = ERROR`。

### Real RAG Integration Test

当 RAG Retriever 可调用时，增加独立的 Integration Test：

1. 能够导入真实 Retriever。
2. Retriever 接受 Financial Filters。
3. Retrieval Results 可以转换成内部 Evidence 格式。
4. Source Metadata 得到保留。
5. Workflow 返回符合约定的结构。

真实 Integration Tests 可能需要数据库、外部服务或其他依赖，因此应与 Mock Tests 分开。

### Development Rules

1. 使用 pytest。
2. Mock Tests 必须可重复。
3. 不允许 Hardcode 测试成功结果。
4. 未经沟通不修改其他组员的 Production Modules。
5. 发现 Interface Mismatch 及时反馈 Team Leads。
6. 迁移时保留已有可运行的测试。
7. LangGraph Workflow 完成后增加 Integration Tests。
8. MVP Tests 不依赖 LLM API Credentials。

### Acceptance Criteria

- Module Unit Tests 全部通过。
- 三个 MVP Workflow Scenarios 全部通过。
- 验证 LangGraph Execution。
- 保留 Source Metadata。
- Logs 正确反映 Tool Calling Order。
- Mock Tests 无需外部 API Credentials。

---

## 9. Team Lead Responsibilities — 组长职责

**负责人：** Agentic Backbone Team Leads

**文件：**

- `agent/workflow.py`
- `agent/state.py`（最终 Schema 审批）
- `main.py`
- `requirements.txt`

### Responsibilities

1. 维护整体 Architecture。
2. 实现 Main LangGraph `StateGraph`。
3. 为组员函数创建 Node Wrappers。
4. 定义 Edges 和 Conditional Edges。
5. 协调 Shared State Updates。
6. 集成 RAG Retrieval。
7. 实现 Workflow-level Exception Handling。
8. 连接 Execution Logging。
9. Review 和 Merge Member Pull Requests。
10. 运行 End-to-End Tests。
11. 准备 Oct 22 Demo。

### Main Workflow Interface — 主工作流接口

保留：

```python
def run_agent(
    query: str,
    top_k: int = 10
):
    """Execute the financial retrieval workflow."""
```

最终返回类型为 LangGraph-compatible State Dictionary。

旧版 Dataclass Workflow 可以暂时保留，作为 Backward Compatibility。

### LangGraph Graph Structure — 主工作流结构

```text
START
  |
Query Understanding
  |
RAG Retrieval
  |
Conditional Routing
  |
  +-- SUCCESS ------> END
  |
  +-- NO_EVIDENCE --> END
  |
  +-- ERROR --------> END
```

Team Leads 负责确保：

- Node Wrappers 正确调用模块函数。
- Exceptions 被捕获并记录。
- 预期的检索失败会得到 `ERROR` Status。
- Graph 不会因为一个可以处理的工具错误而直接中断、丢失状态。

### Dependency Management — 依赖管理

Team Leads 负责更新 `requirements.txt`。

在迁移测试通过前，不要直接删除旧版 LangChain Dependencies。

---

## 10. Cross-Team Dependencies — 跨组依赖

### RAG Team

**Priority：High（高）**

需要：

- Callable Retriever
- Python Import Instructions
- RetrievedChunk Schema
- Metadata Filtering Behavior
- Source IDs and Citations
- Sample Financial Question

期望结果：

能够通过我们的 RAG Adapter 成功执行一次真实 Retrieval Call。

### GraphRAG Team

**Priority：Planning（规划）**

需要：

- 计划中的 Graph Retrieval Interface
- 支持的 Entity / Relationship Queries
- Graph Evidence Format
- Missing Relationship / Abstention Behavior

期望结果：

记录未来 GraphRAG Integration 的接口需求。

Oct 22 不要求完成 Live GraphRAG Integration。

### Business / UI Team

**Priority：Interface Alignment（接口对齐）**

需要：

- User Question Request Format
- Evidence / Citation Display Requirements
- Error / No-Evidence Display
- Future Answer Generation Requirements

期望结果：

双方确认初步 UI-to-Agent Request / Response Contract。

Oct 22 暂不要求完成整个 UI Integration。

### Evaluation Team

**Priority：Testing Alignment（测试对齐）**

需要：

- Shared Test Questions
- Expected Evidence Format
- Citation Requirements
- No-answer Cases
- Evaluation Metrics

期望结果：

保证 Agent Workflow 和 Retrieval Tests 使用一致的定义。

---

## 11. October 22 Deliverables — 交付标准

Oct 22 MVP 最低应展示：

1. 用户输入 Financial Question。
2. Workflow 提取 Financial Filters。
3. Agent 调用 Retriever。
4. Retriever 返回 Evidence 或 Empty Result。
5. Workflow 正确处理 Success、No Evidence 和 Error。
6. Source Metadata 得到保留。
7. Execution Logs 显示实际执行步骤。
8. 可以检查 Final Workflow Result。
9. Automated Tests 通过。

### Preferred Demo — 首选方案

调用 RAG Team 的真实 Retriever，使用真实 SEC Evidence。

### Fallback Demo — 备用方案

如果跨组集成仍不稳定，使用 Deterministic Mock Retriever。

展示时必须明确区分 Mock Results 和 Real SEC Evidence。

### Out of Scope — 本次不要求

- 完整 Hierarchical Multi-Agent Execution
- GraphRAG Production Integration
- SQL Tools
- LLM-generated Financial Answers
- Full UI Deployment
- Persistent Chat Sessions

---

## 12. Development Timeline — 时间线

| Date | Task | Deliverable |
|---|---|---|
| Oct 15–16 | Architecture / Contract Revision | 更新技术文档 |
| Oct 19 | Module Development | 五个初版 Module PRs |
| Oct 20 | Workflow Integration | 第一个 End-to-End Workflow |
| Oct 21 | Testing / Debugging | Regression Tests |
| Oct 22 | MVP Presentation | Working LangGraph-based Demo |

---

## 13. Future Multi-Agent Extensions — 未来扩展

长期架构可能包含：

- Supervisor Agent
- RAG Retrieval Agent
- GraphRAG Retrieval Agent
- Structured Data / SQL Agent
- Answer Synthesis Agent

### Future State Fields

- `selected_tools`
- `agent_messages`
- `tool_results`
- `answer`
- `citations`
- `execution_trace`

### Future Capabilities

1. Hierarchical Task Delegation
2. Multi-tool Retrieval
3. Evidence Aggregation
4. Evidence Sufficiency Evaluation
5. Citation Validation
6. Grounded LLM Answer Generation
7. Abstention
8. Multi-Agent Observability

未来增加这些功能时，需要同步更新 Function Contracts 和 Acceptance Tests。

不要在尚未确认 Architecture 的情况下，各组员独立添加复杂功能。

---

## 14. Final Development Principles — 最终开发原则

1. **Build a stable MVP first**：先保证基础工作流稳定。
2. **Use LangGraph for orchestration**：LangGraph 负责工作流，不重复开发模块逻辑。
3. **Keep modules independently testable**：每个函数都应能够独立测试。
4. **Team Leads maintain the main graph**：统一维护主 Graph。
5. **Members may learn and use LangGraph**：所有成员都可以学习和尝试 LangGraph。
6. **Preserve evidence provenance**：保留 Evidence 来源和 Citation Metadata。
7. **Make tool calling observable**：记录工具调用过程。
8. **Distinguish no evidence from errors**：区分证据不足与程序报错。
9. **Prefer reusable interfaces**：不要为了 Demo Hardcode 功能。
10. **Coordinate contract changes**：接口变更必须提前沟通。

---

## 15. Current Implementation Status — 当前实现状态

### Completed — 已完成

- GitHub Repository Structure
- Initial Module Contracts
- Original Shared-State Dataclass
- LangChain Core Workflow Skeleton
- Mock Retrieval Tests

### In Progress / Planned — 进行中或计划中

- LangGraph StateGraph Implementation
- TypedDict-based Shared State
- Updated Routing / Logging Support
- Five Member Module Implementations
- Real RAG Integration
- LangGraph Integration Tests

### Future Scope — 未来范围

- Hierarchical Multi-Agent
- GraphRAG Integration
- SQL Retrieval Tools
- LLM Answer Synthesis
- Production UI Integration

**这份文档定义的是目标接口和开发标准，并不代表所有 LangGraph 组件都已经完成开发。**

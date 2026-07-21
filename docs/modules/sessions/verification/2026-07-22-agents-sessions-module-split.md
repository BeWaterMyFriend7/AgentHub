# Agents / Sessions 第一阶段模块拆分验证

## 范围

验证现有 Mock 会话应用拆分为 `agents`、`sessions` 和应用组合入口后，统计、精确恢复、接入探测、事件记录、路由和旧导入兼容行为保持可用。

## 环境

- 操作系统：Windows
- Python：项目 `.venv`
- 应用版本：`0.1.0`（本阶段只调整内部结构，不改变产品版本）
- 数据源：Mock Agent Adapter 与 Demo Seed

## 验证命令与结果

```powershell
$env:PYTHONPATH="$PWD\src"
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

结果：9 个测试全部通过，覆盖 Agent Profile 唯一性、无 Session Adapter 的 Profile、会话统计、精确恢复与事件、未知 Agent 探测、应用路由、真实 API 响应、404 行为和旧导入路径。

```powershell
.venv\Scripts\python.exe -m compileall -q src tests
node --check src\agent_hub\static\app.js
```

结果：Python 编译检查和前端 JavaScript 语法检查通过。

使用 FastAPI `TestClient` 验证 `/api/sessions`、`/api/agents/{agent_id}/probe`、`/api/tools/{tool_id}/probe` 和未知会话打开；另使用 Uvicorn 在 `127.0.0.1:17861` 临时启动并请求 `/api/summary` 与 `/api/agents`。

结果：新 API 只返回 `agent_id`、`agent_name`，旧探测入口只返回 `tool_id`；未知会话返回 404。HTTP 验证通过，返回 6 个内部会话和 3 个 Agent Profile；验证后已停止临时进程。

## 已知缺口

- 当前仍使用 Mock Adapter，不能作为真实 Agent 完整接入证据。
- 旧 Python 导入路径与 `/api/tools` 仍保留兼容，待真实 Adapter 和新模块稳定后删除。
- Capabilities 与 Operations 尚未进入代码拆分阶段。

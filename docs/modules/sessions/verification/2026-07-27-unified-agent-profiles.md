# 统一 Agent Profile 与 OpenCode Desktop 验证

## 验证目标

- 默认运行时同时加载多个真实 Agent Profile。
- Codex Desktop 与 OpenCode Desktop 分别发现和识别会话状态。
- OpenCode Desktop 不依赖随机生成的 HTTP Server 密码。
- Profile 配置页面支持新增、编辑、启停、删除和独立探测。
- 同一 Agent 产品的 Desktop 与 Server 接入不合并身份。

## 本机环境

- Codex 数据：`C:\Users\BeWater\.codex`。
- OpenCode Desktop 数据：`C:\Users\BeWater\.local\share\opencode\opencode.db`，约 2.68 GB。
- OpenCode Desktop 程序：`C:\Users\BeWater\AppData\Local\Programs\@opencode-aidesktop\OpenCode.exe`。
- OpenCode CLI：`opencode`，支持 `--session <session-id>`。
- OpenCode Desktop HTTP Server：`127.0.0.1:10190`，认证密码随进程随机生成；本实现未读取或保存该密码。

## 自动化结果

执行：

```powershell
$env:PYTHONPATH = "$PWD\src"
.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check src\agent_hub\static\app.js
```

结果：44 项 Python 测试全部通过，前端脚本语法检查通过。

## 真实扫描结果

两个默认 Profile 探测均通过：

- `codex-desktop`：验证本地任务发现、rollout 生命周期状态与 Desktop 深链。
- `opencode-desktop`：验证 Desktop SQLite 表、顶层会话、Todo 与 CLI 恢复入口。

连续执行两次统一扫描：

```text
session_count 200
stable_ids True 200
by_agent {'codex-desktop': 100, 'opencode-desktop': 100}
by_status {'executing': 2, 'closed': 100, 'interrupted': 20, 'unknown': 78}
```

`unknown` 是保守结果：OpenCode 最近一轮 assistant 回复已经结束但会话尚未归档时，不推断整个任务已完成。

## 浏览器验收

- Dashboard 显示 `2 / 2 已连接` 与 200 个真实会话。
- 页面无浏览器控制台错误。
- 新增 Profile 可切换 Codex Desktop、OpenCode Desktop、OpenCode CLI / Server，并动态展示对应字段。
- OpenCode Server 表单只要求密码环境变量名。
- OpenCode Desktop 页面探测通过，显示 100 个顶层会话、表结构与 CLI 恢复检查。
- Dashboard 一次请求只扫描一次 Adapter，自动刷新间隔为 30 秒。

## 能力边界

- OpenCode Desktop 的完成状态只在会话归档时标记为 `closed`；普通回合结束保持 `unknown`。
- OpenCode Desktop 恢复通过 CLI/TUI 按原生 ID 打开，不声明 Desktop 专用深链。
- OpenCode Server 仅声明恢复命令可启动；人工确认目标 TUI 内容前不声明完整精确恢复。
- Codex 与 OpenCode 当前均采用周期扫描，不声明事件流能力。
- 会话跟进标记本轮未实现。

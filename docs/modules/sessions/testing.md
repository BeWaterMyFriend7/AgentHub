# Sessions 模块测试策略

## 单元测试

- 原生状态到统一运行状态的映射。
- 运行状态与关注状态相互独立。
- 等待授权、等待输入、等待验收和执行中断的进入与解除条件。
- 规划缺失、状态来源和可信度的展示模型。
- 用户跟进标记、标签、备注和提醒时间的持久化与取消。
- 用户跟进标记不改变原生运行状态或系统关注状态。

## Adapter 契约测试

用统一夹具验证每个 Agent Adapter 的多会话发现、稳定原生 ID、独立状态、规划缺失行为、事件增量、接入等级和精确恢复。至少同时启动三个内部会话，确认身份与状态互不串扰。

## 集成测试

- 事件更新、周期扫描和手动刷新得到一致结果。
- Agent 重启、会话关闭、数据源暂时不可用和重复事件不会生成重复会话。
- 精确恢复始终携带目标原生会话 ID；只激活首页或窗口必须判为有限接入。

## API 与 UI 验收

- 会话总数和状态统计按内部会话计算。
- 待处理汇总、来源、可信度和有限接入提示正确。
- Agent 未提供规划时不显示虚假步骤或百分比。
- AgentHub 页面不出现直接回复或批准权限入口。
- 系统关注和用户跟进可以分别筛选，刷新后用户标记仍存在。

## BDD

- [`session-observation.feature`](./bdd/session-observation.feature)：会话发现、统计、规划和精确恢复。
- [`session-attention.feature`](./bdd/session-attention.feature)：待处理识别、自动解除和状态可信度。

## OpenCode 契约与真实验证

- 使用 `httpx.MockTransport` 验证多会话解析、稳定身份、状态映射、Todo、最近活动和认证脱敏。
- 公共契约测试验证重复扫描不改变会话身份，精确恢复目标始终包含原生会话 ID。
- 真实验证脚本为 `scripts/verify_opencode_sessions.py`，密码只通过 `OPENCODE_SERVER_PASSWORD` 环境变量提供。
- 真实验证至少运行两次扫描，启动一个指定原生会话的恢复进程，并由人工确认 TUI 内容；历史会话状态缺失时必须显示 `unknown`。

## Codex 契约与真实验证

- 使用临时 SQLite 和 rollout JSONL 验证 `task_started`、`request_user_input`、`task_complete`、`turn_aborted` 与统一状态的映射。
- 验证 `request_user_input` 收到对应调用结果后恢复为 `executing`，缺失 rollout 时降级为 `unknown`。
- 公共契约测试验证重复扫描保持稳定 Thread ID，精确定位目标始终包含原生 Thread ID。
- 真实验证脚本为 `scripts/verify_codex_sessions.py`，默认读取 `CODEX_HOME` 或 `~/.codex`，不需要认证信息。
- 真实验证至少运行两次扫描，同时检测一个运行中任务和一个带 `task_complete` 证据的历史任务；可用 `--open-session <thread-id>` 验证 Desktop 深链定位。

## OpenCode Desktop 契约与真实验证

- `test_opencode_desktop_adapter.py` 使用临时 SQLite 验证执行中、中断、已归档和未知状态，验证 Todo、最近活动、稳定 ID 与 CLI Resume 原生 ID。
- 真实环境直接读取本机约 2.68 GB 的 OpenCode Desktop 数据库，不使用 Desktop Server 密码。
- 真实环境连续扫描两次，Codex Desktop 与 OpenCode Desktop 共返回 200 个会话，200 个内部 ID 全部稳定。
- 浏览器验收确认 Dashboard 单次扫描、两个 Profile 连接状态、动态 Profile 表单和 OpenCode Desktop 探测结果正确。

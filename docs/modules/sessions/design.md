# Sessions 模块设计

## 核心模型

`AgentSession` 至少包含：Agent/Profile、内部 ID、稳定原生会话 ID、标题、项目或工作目录、运行状态、系统关注状态、当前目标、计划项、最近活动、更新时间、状态来源、可信度、恢复方式和接入等级。

运行状态回答“会话正在做什么”；系统关注状态回答“可信事件是否表明用户需要介入”；`SessionAnnotation` 保存用户主动添加的跟进标记、标签、备注和提醒时间。三个维度分开存储和展示。

`SessionAnnotation` 是 AgentHub 本地持久化数据，以 `Agent/Profile + 原生会话 ID` 关联会话。Adapter 返回的原生会话快照不得覆盖它，原生状态也不能由用户标记反向修改。

## Agent Adapter 会话契约

每个 Adapter 必须实现或明确声明不支持：

- 列出内部会话并读取单个会话。
- 读取原生状态、规划和增量事件。
- 使用稳定原生会话 ID 精确打开或恢复。
- 探测数据源、连接和恢复能力。
- 返回会话发现、状态、规划、事件和恢复的支持等级。

原生 API、Hook、会话文件和 CLI 细节只存在于 Adapter 内，不泄漏到会话服务或 UI。

## 更新流程

1. 从 `agents` 获取已启用 Profile 和 Adapter。
2. Adapter 发现会话、快照和增量事件。
3. 会话服务以 `Agent/Profile + 原生会话 ID` 归一化身份。
4. 映射运行状态，并基于可信事件推导关注状态。
5. 更新读模型、统计和待处理汇总。
6. 合并本地 `SessionAnnotation`，生成系统关注与用户跟进两个筛选维度。
7. 事件驱动用于实时更新，周期扫描保证最终一致，手动刷新作为兜底。

## 精确恢复

恢复入口按 Agent 官方 API、CLI Resume、原生插件或深度链接、原终端/桌面窗口的顺序降级。只有目标明确绑定原生会话 ID 时才算精确恢复；仅激活窗口标记为有限接入。

进程和窗口探测只用于确认 Agent 是否启动、辅助诊断异常退出，或在原生恢复失败时激活窗口，不能单独判断会话完成或待处理状态。

## 与 Workflows 的关系

Sessions 提供稳定会话身份、归一化事件和精确恢复 Interface。Workflows 保存任务执行与会话的关联，并消费可信会话事件判断任务是否完成；Sessions 不保存队列顺序，也不触发下一任务。

## 当前实现

- `src/agent_hub/sessions/models.py`：会话、状态、规划、事件与统计模型。
- `src/agent_hub/sessions/hub.py`：会话聚合、统计、待处理和精确恢复 Interface。
- `src/agent_hub/sessions/adapters/`：会话发现、接入探测与精确恢复 seam。
- `src/agent_hub/sessions/events.py`：当前内存事件记录实现。
- `src/agent_hub/demo/seed.py`：仅供 Mock 演示使用的数据，不属于生产事实来源。
- `src/agent_hub/demo/controller.py`：编排 Mock 状态推进；该能力不进入通用 Session Adapter 契约。

## OpenCode 映射

`OpenCodeSessionAdapter` 使用官方 Server API，并以 `Agent Profile ID + 原生会话 ID` 生成稳定内部身份。工作目录来自 OpenCode `location.directory`，项目名只取该目录名称；Todo 和最近消息文本均读取原生响应，不生成推测步骤。

- `running` 或 `busy` 映射为 `executing`。
- `retry` 保留原生重试消息并映射为 `executing`。
- `idle` 映射为 `unknown`，原因中保留原生 idle，不推断为等待输入或已完成。
- 不在活动结果中的历史会话标记为 `unknown`，原因中保留 inactive，不推断为已关闭。

精确恢复使用 `opencode attach <endpoint> --session <native_session_id> --dir <directory>`。认证通过进程环境变量传入，不出现在命令行、API 响应或事件记录中。

## Codex 映射

`CodexSessionAdapter` 只读 Codex Desktop 本地状态，不要求 API Key、ChatGPT 登录信息或额外 Server。稳定任务元数据来自 `CODEX_HOME` 中版本号最大的 `state_*.sqlite` 的 `threads` 表，轮次状态、规划和最近活动来自每个任务的 `rollout-*.jsonl`。

- 最近生命周期事件为 `task_started`，且没有后续完成或中断事件时映射为 `executing`；由于异常退出可能来不及写入终止事件，该状态可信度为中等。
- 当前轮次存在尚未返回的 `request_user_input` 调用时映射为 `waiting_input`。
- `task_complete` 映射为 `closed`，只表示当前轮次已结束，任务仍可继续发送后续内容。
- `turn_aborted` 映射为 `interrupted`。
- rollout 缺失、损坏或尾部没有完整生命周期证据时映射为 `unknown`，不根据窗口、进程或更新时间推断完成。

规划只读取当前轮次最近一次 `update_plan` 的原生参数。精确定位使用 Codex Desktop 注册的 `codex://threads/<native_thread_id>` 深链；深链包含稳定原生 Thread ID，不依赖窗口标题或最近任务。

当前接入采用周期扫描，不声明 Codex App Server 内存事件流能力。等待授权状态主要存在于 App Server 运行时通知，尚未找到可供 AgentHub 独立进程稳定读取的持久化证据，因此首版不推断 `waiting_permission`。

## OpenCode Desktop 映射

`OpenCodeDesktopSessionAdapter` 不连接 Desktop 内置 HTTP Server，因此不需要读取其每次启动随机生成的认证密码。Adapter 以只读方式打开 `~/.local/share/opencode/opencode.db`，读取顶层 `session`、`message`、`part` 和 `todo`，并使用 `Agent Profile ID + 原生会话 ID` 生成稳定内部身份。

- 会话已归档时映射为 `closed`。
- 最近 assistant 消息没有完成时间时映射为 `executing`。
- 最近响应包含原生 `error` 时映射为 `interrupted`，并保留错误类型。
- 最近消息来自用户且尚未观察到 assistant 完成事件时映射为 `executing`，可信度为中等。
- 最近 assistant 响应已结束但会话未归档时映射为 `unknown`，不根据回复文字或 Todo 猜测任务已经完成。

Todo 状态按原生 `completed/in_progress/pending/cancelled` 映射。恢复入口使用共享同一会话数据库的官方命令 `opencode <directory> --session <native_session_id>`；该入口精确携带原生 ID，但当前打开的是 CLI/TUI，不冒充 OpenCode Desktop 深链。

Dashboard API 在一次刷新中只扫描一次所有 Adapter，再同时生成统计、待处理和会话列表。单个 Adapter 读取失败会记录事件并将对应 Profile 标为断开，不影响其他 Profile 的会话返回。

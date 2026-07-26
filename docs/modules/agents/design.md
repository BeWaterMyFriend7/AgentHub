# Agents 模块设计

## 职责

Agents 是接入层的领域入口，维护 Agent 身份、安装、Profile 和 Adapter 注册表。它不负责解释会话状态、编排任务，也不直接执行能力共享或删除。

## 核心模型

- `AgentType`：Codex、Claude Code、OpenCode 等产品类型。
- `AgentInstallation`：本机发现的一份安装，包含版本、可执行文件和平台信息。
- `AgentProfile`：用户启用的接入配置，引用安装并保存 Adapter 参数。
- `AgentCapabilityMatrix`：会话观察、任务执行、Skill、MCP、插件的支持状态、限制和验证等级。
- `AdapterRegistration`：Agent 类型到 Adapter 工厂及其版本约束的注册关系。

## 对外接口

- 查询已启用 Profile 和稳定 Agent ID。
- 校验 Profile 的连接、目录、配置和恢复入口。
- 获取某 Agent 对会话观察、任务执行或某类能力的支持声明。
- 为 `sessions`、`workflows` 和 `capabilities` 创建对应 Adapter。

## 依赖边界

- `sessions` 通过 Agent Adapter 会话契约读取会话和执行精确恢复。
- `workflows` 通过 Agent 执行 Adapter 新建会话、继续指定会话并发送用户确认的任务。
- `capabilities` 通过 Agent Adapter 能力契约获取发现位置、原生注册方式和加载状态。
- `operations` 使用已校验的 Profile 和 Adapter 执行原生变更。
- UI 不直接解释 Agent 原生配置，也不直接调用系统命令。

## 持久化

数据库保存 Profile、用户选择、能力声明缓存和验证记录；Agent 安装、原生 API、配置文件和文件系统仍是事实来源。每次连接验证应刷新缓存并保留失败原因。

## 当前实现

- `src/agent_hub/agents/models.py`：Agent Profile、配置输入与会话接入能力声明。
- `src/agent_hub/agents/config.py`：Profile JSON 持久化与首次候选配置。
- `src/agent_hub/agents/registry.py`：运行时 Profile 查询与连接状态更新 Interface。
- `src/agent_hub/adapter_factory.py`：Adapter 类型目录、Profile 标准化与真实 Adapter 构造。
- `src/agent_hub/bootstrap.py`：在应用组合入口创建可重载 Registry 和 SessionHub。

当前 Adapter 只覆盖会话发现和恢复，因此作为 Session Adapter 放在 `sessions` 模块，避免 `agents` 反向依赖会话模型。未来出现跨会话、能力等多个真实 Adapter 实现后，再从已验证的共同点提取更高层 Agent Adapter。

## OpenCode 注册

OpenCode Server 保留 `create_opencode_runtime` 作为验证和兼容入口；生产默认运行时通过 `AgentAdapterFactory` 从 Profile 注册。Profile 只保存 Server 地址、密码环境变量名、能力声明和状态来源；Basic Auth 密码由运行时注入 Adapter，不进入 Profile、日志或恢复目标。

- 会话发现：完整支持，来源为 OpenCode Server `/api/session`。
- 独立状态：轮询支持；运行中状态可直接映射，历史 inactive/idle 不推断为完成。
- Todo 读取：完整支持，来源为 `/session/{sessionID}/todo`。
- 精确恢复：官方 CLI 命令和进程存活已验证，仍待人工确认 TUI 展示了指定会话内容。
- 事件流：首版未接入，声明为不支持，使用轮询保证最终刷新。

## Codex 注册

Codex 保留 `create_codex_runtime` 作为验证和兼容入口；生产默认运行时自动发现本机 Codex Desktop Profile。Profile 只声明本地状态轮询和 Desktop 深链能力，不保存账号、Token 或 API Key。

- 会话发现：完整支持，来源为 `CODEX_HOME` 中版本号最大的 `state_*.sqlite`。
- 独立状态：支持 rollout 生命周期轮询，可识别执行中、等待输入、已结束和中断。
- 规划读取：支持当前轮次最近一次 `update_plan`。
- 精确恢复：使用 `codex://threads/<thread-id>` 在 Codex Desktop 中定位原生任务。
- 事件流：首版未接入，声明为不支持；等待授权等只存在于 App Server 内存通知的状态暂不推断。

## 统一 Profile 配置实现

生产入口使用 `create_configured_runtime`，不再默认启动 Demo Runtime。`AgentProfileStore` 将配置保存到 `~/.agenthub/agents.json`，支持新增、编辑、启停和删除；首次没有配置文件时自动生成 Codex Desktop 与 OpenCode Desktop 候选 Profile。

产品类型与接入 Profile 分开建模。同一 OpenCode 产品可以同时存在 `opencode_desktop` 与 `opencode_server`，两者使用独立 Profile ID、连接状态和会话身份，不按显示名称合并。`AgentAdapterFactory` 根据 `adapter_kind` 构造 Adapter，单个 Profile 配置错误不会阻断其他 Profile。

OpenCode Server Profile 只保存 `secret_env`，例如 `OPENCODE_SERVER_PASSWORD`；密码值只在构造 Adapter 时从进程环境读取，不写入 JSON、API 响应、日志或恢复命令。页面提供以下接入类型：

- `codex_desktop`：Codex 本地状态与 Desktop 深链。
- `opencode_desktop`：OpenCode Desktop 本地 SQLite 与官方 CLI Resume。
- `opencode_server`：OpenCode Server API 与 CLI Attach。

OpenCode Server 的 `resume_launch` 为已验证，`exact_resume` 在人工确认目标 TUI 内容前保持 `false`；两者不得因为使用了同一个 CLI 参数而合并声明。

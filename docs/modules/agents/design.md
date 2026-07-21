# Agents 模块设计

## 职责

Agents 是接入层的领域入口，维护 Agent 身份、安装、Profile 和 Adapter 注册表。它不负责解释会话状态，也不直接执行能力共享或删除。

## 核心模型

- `AgentType`：Codex、Claude Code、OpenCode 等产品类型。
- `AgentInstallation`：本机发现的一份安装，包含版本、可执行文件和平台信息。
- `AgentProfile`：用户启用的接入配置，引用安装并保存 Adapter 参数。
- `AgentCapabilityMatrix`：会话、Skill、MCP、插件的支持状态、限制和验证等级。
- `AdapterRegistration`：Agent 类型到 Adapter 工厂及其版本约束的注册关系。

## 对外接口

- 查询已启用 Profile 和稳定 Agent ID。
- 校验 Profile 的连接、目录、配置和恢复入口。
- 获取某 Agent 对会话或某类能力的支持声明。
- 为 `sessions` 和 `capabilities` 创建对应 Adapter。

## 依赖边界

- `sessions` 通过 Agent Adapter 会话契约读取会话和执行精确恢复。
- `capabilities` 通过 Agent Adapter 能力契约获取发现位置、原生注册方式和加载状态。
- `operations` 使用已校验的 Profile 和 Adapter 执行原生变更。
- UI 不直接解释 Agent 原生配置，也不直接调用系统命令。

## 持久化

数据库保存 Profile、用户选择、能力声明缓存和验证记录；Agent 安装、原生 API、配置文件和文件系统仍是事实来源。每次连接验证应刷新缓存并保留失败原因。

## 当前实现

- `src/agent_hub/agents/models.py`：Agent Profile 与会话接入能力声明。
- `src/agent_hub/agents/registry.py`：Agent Profile 的统一读取 Interface。
- `src/agent_hub/bootstrap.py`：在应用组合入口创建 Registry，不在业务模块内部创建依赖。

当前 Adapter 只覆盖会话发现和恢复，因此作为 Session Adapter 放在 `sessions` 模块，避免 `agents` 反向依赖会话模型。未来出现跨会话、能力等多个真实 Adapter 实现后，再从已验证的共同点提取更高层 Agent Adapter。

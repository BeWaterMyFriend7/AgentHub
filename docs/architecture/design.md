# AgentHub V1 系统级设计

## 文档目的

本文只描述 AgentHub 的系统边界、模块关系、依赖方向和公共基础设施。模块内部的详细需求、模型、流程和测试放在 [`../modules/`](../modules/README.md)；已经落地的现状以 [`overview.md`](./overview.md) 为准；难以逆转的选择记录在 [`adr/`](./adr/) 中。

## 设计目标

- 最终只运行一个 AgentHub 应用，内部采用模块化单体。
- 聚合多个 Agent 的内部会话，并精确恢复指定会话。
- 统一管理 Skill、MCP Server 和 Agent 插件，但保留类型专属语义。
- 支持 Windows、macOS、Linux 主流桌面系统。
- 文件系统和 Agent 原生 API/配置是事实来源。
- 所有破坏性操作可预检、可审计，并具有明确恢复等级。

## 模块关系

```text
API / UI
├── agents
├── sessions ──────> agents
├── capabilities ──> agents
└── operations ────> agents + capabilities

agents / sessions / capabilities / operations
  -> Agent Adapter / Platform Adapter
  -> Agent API / Hook / 配置 / CLI / 文件系统
```

- [`agents`](../modules/agents/README.md) 提供 Agent 身份、Profile、支持矩阵和 Adapter 注册。
- [`sessions`](../modules/sessions/README.md) 只处理会话读模型、状态、待处理和精确恢复。
- [`capabilities`](../modules/capabilities/README.md) 统一表达 Skill、MCP、插件的来源、安装和加载状态。
- [`operations`](../modules/operations/README.md) 执行所有有副作用的文件、配置和生命周期操作。

`sessions` 与 `capabilities` 可以独立读取 Agent 原生事实；写操作必须经过 `operations`。`operations` 读取 Agent 支持能力和能力所有权，但不定义这些业务对象。

## 公共基础设施

- API/UI：只调用应用服务并展示归一化模型，不包含原生格式解析或系统命令。
- Repository：保存 Profile、索引、快照、操作计划和审计；不取代外部事实来源。
- Agent Adapter：隔离不同 Agent 的 API、Hook、配置、目录和 CLI 差异。
- Platform Adapter：隔离 Windows Junction 与 macOS/Linux Symbolic Link 等平台差异。
- 事件与扫描：事件驱动提供实时性，周期扫描保证最终一致，手动刷新作为兜底。
- 本地安全：仅监听本机，限制允许路径，隐藏秘密，对修改请求执行本地授权保护。

## 事务与一致性

跨文件系统和 Agent 原生配置无法依赖单一数据库事务。修改操作使用“操作计划 + 分步审计 + 补偿动作 + 最终重新扫描”实现可恢复的最终一致性。数据库中的状态不是操作成功的唯一判断，必须验证文件系统和 Agent 原生加载结果。

## 代码组织方向

`src/agent_hub/` 继续作为唯一应用包，后续按四个业务模块组织内部包，并保留共享的 `api`、`storage`、`platform` 等基础设施。SkillBridge 的成熟逻辑按职责迁入 `capabilities` 或 `operations`，不整体嵌入为第二套应用；逐文件处理结论见 [SkillBridge 迁移记录](../modules/capabilities/references/skill-bridge-migration.md)。

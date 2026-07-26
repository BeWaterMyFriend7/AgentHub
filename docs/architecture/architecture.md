# AgentHub 系统架构

本文维护 AgentHub 当前运行结构、目标模块关系、依赖方向和公共基础设施。模块内部需求和设计归所属模块维护，长期架构决策归 [`adr/`](./adr/) 维护。

## 当前运行结构

```text
浏览器 UI
  -> FastAPI 应用工厂（src/agent_hub/main.py）
  -> 运行时组合（src/agent_hub/bootstrap.py）
       ├── agents/AgentRegistry
       ├── sessions/SessionHub
            ├── sessions/adapters/MockSessionAdapter
            └── sessions/SessionEventLog
       └── demo/DemoSessionController（仅演示状态推进）
```

当前代码已经形成模块化单体骨架：`agents` 与 `sessions` 已进入应用运行时；`capabilities` 提供只读 Skill 发现与统一能力模型；`operations` 提供共享安装的预检、确认、备份、目录链接、验证、回滚与审计；`platform` 隐藏 Windows Junction 和 macOS/Linux Symbolic Link 差异。

旧的会话 `models.py`、`service.py`、`repository.py`、`seed.py` 和 `adapters/` 暂时作为迁移兼容层。核心模型和新 Interface 统一使用 `agent_id`、`agent_name`；`tool_id` 等旧术语只保留在兼容入口。Demo 状态推进不属于生产 Session Adapter 契约。

历史 SkillBridge 的领域逻辑已提取到 AgentHub，其独立应用源码已从 `src/` 移除。Capabilities 与 Operations 暂未接入 HTTP Interface/UI，也尚未实现 MCP、插件、来源删除和持久化审计。`workflows` 当前只有需求和设计文档，尚未进入源码实现。

## 目标模块关系

```text
API / UI
├── agents
├── sessions ──────> agents
├── workflows ─────> agents + sessions
├── capabilities ──> agents
└── operations ────> agents + capabilities

业务模块
  -> Agent Adapter / Platform Adapter
  -> Agent Interface / Hook / 配置 / CLI / 文件系统
```

- [`agents`](../modules/agents/README.md) 提供 Agent 身份、Profile、支持矩阵和 Adapter 注册。
- [`sessions`](../modules/sessions/README.md) 处理会话读模型、运行状态、系统关注状态、用户跟进标记和精确恢复。
- [`workflows`](../modules/workflows/README.md) 处理任务队列、顺序推进、暂停策略、执行状态和结果会话关联。
- [`capabilities`](../modules/capabilities/README.md) 表达 Skill、MCP、插件的来源、安装和原生加载状态。
- [`operations`](../modules/operations/README.md) 执行改变文件系统、Agent 原生配置或安装状态的安全操作。

`sessions` 不承担任务调度；`workflows` 消费归一化会话事件并引用稳定会话身份。写入 Agent 工作内容由 Workflows 执行 Adapter 负责，原生协议细节不得泄漏到业务模块或 UI。

## 公共基础设施

- API/UI：只调用模块 Interface 并展示归一化模型，不解释原生格式或执行平台命令。
- Repository：保存 Profile、用户标记、工作流、快照、操作计划和审计；不取代外部事实来源。
- Agent Adapter：隔离不同 Agent 的 Interface、Hook、配置、目录和 CLI 差异。
- Platform Adapter：隔离 Windows Junction 与 macOS/Linux Symbolic Link 等平台差异。
- 事件与扫描：事件驱动提供实时性，周期扫描保证最终一致，手动刷新作为兜底。
- 本地安全：统一约束本机监听、允许路径、秘密隐藏和修改请求保护；具体业务操作规则由所属模块维护。

## 事务与一致性

跨文件系统、Agent 原生配置和任务执行无法依赖单一数据库事务。修改操作使用“操作计划 + 分步审计 + 补偿动作 + 最终重新扫描”；任务编排使用持久化状态机、幂等推进和明确暂停策略。数据库状态不能单独证明外部操作成功，必须验证文件系统、Agent 原生加载结果或可信会话事件。

## 代码组织方向

`src/agent_hub/` 是唯一应用包，业务代码按 `agents`、`sessions`、`workflows`、`capabilities` 和 `operations` 组织，并保留共享的 API、Storage、Platform 等基础设施。只有出现真实变化点时才提取新的 Adapter seam，避免为单一实现增加无效转发层。

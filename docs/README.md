# AgentHub 文档索引

AgentHub 是面向 Windows、macOS、Linux 的本地 AI Agent 管理中枢。它集中观察和恢复 Agent 内部会话，编排可连续执行的任务，并管理 Skill、MCP Server 与 Agent 插件等本地能力。

## 产品规划范围

已确认的产品规划包含；当前实现进度以[系统架构](./architecture/architecture.md#当前运行结构)和[路线图](./process/roadmap.md)为准：

- 本地单用户、单个 AgentHub 应用。
- Codex、Claude Code、OpenCode 及后续 Agent 的统一接入。
- 内部会话发现、状态观察、系统关注状态、用户跟进标记和精确恢复。
- 跨项目任务排队、顺序执行、暂停处理、状态展示和结果会话定位。
- Skill、MCP Server、Agent 插件的发现、共享、安全变更、审计和恢复。
- Windows、macOS、Linux 平台适配。

当前不包含云端同步、团队权限和组织策略分发。每项业务需求由所属模块的 `requirements.md` 维护；跨模块结构和公共约束由系统架构维护，难以逆转的决策记录为 ADR。

## 产品边界变化

早期会话 MVP 只观察状态并精确打开原生会话，不在 AgentHub 内发送消息，也不提供人工会话标记。当前规划将任务排队作为 Workflows 的受控能力，将人工跟进标记作为 Sessions 的本地元数据能力；具体业务规则分别由 [Workflows 需求](./modules/workflows/requirements.md)和 [Sessions 需求](./modules/sessions/requirements.md)维护。

任务发送、会话观察和项目上下文的模块归属见 [ADR-0009](./architecture/adr/0009-workflows-and-session-follow-up-boundary.md)。

## 文档结构

| 目录 | 回答的问题 | 主要入口 |
| --- | --- | --- |
| `architecture/` | 当前系统如何组成、目标结构是什么、为什么这样决策 | [`architecture.md`](./architecture/architecture.md)、[`adr/`](./architecture/adr/) |
| `modules/` | 每个模块做什么、如何实现、怎样测试与验证 | [`modules/README.md`](./modules/README.md) |
| `process/` | 下一步做什么、当前待办、已经学到什么 | `roadmap.md`、`todo.md`、`learnings.md` |
| `guides/` | 如何运行、开发和维护 | [`guides/README.md`](./guides/README.md) |
| `prototypes/` | 非生产 UI 和技术实验 | `agent-hub-v1.md`、`agent_hub_prototype_v3.html` |

## 文档职责

- 模块 `requirements.md` 是该模块业务范围、规则和验收条件的事实来源。
- 模块 `design.md` 描述内部模型、Interface、流程以及与其他模块的依赖。
- 模块 `testing.md` 描述自动化测试、契约测试、集成测试和 UI/API 测试策略。
- 模块 `bdd/` 可选，用业务语言描述复杂且稳定的外部可观察行为，不保存执行结果。
- 模块 `verification/` 只保存真实 Agent、平台或文件系统验证证据；没有实际记录时不创建占位目录。
- 模块 `references/` 保存历史方案、迁移记录和研究材料，不作为当前需求或设计事实来源。
- [`architecture/architecture.md`](./architecture/architecture.md) 同时维护当前结构和目标结构，避免现状与设计分散后失去同步。
- ADR 只记录重要、难以逆转且存在真实取舍的决策；变化时新增 ADR，并标记旧 ADR 被取代。
- 原型仅用于参考，不得被生产代码依赖。

## 推荐阅读顺序

```text
docs/README.md
  -> architecture/architecture.md
  -> modules/README.md
  -> modules/<module>/requirements.md
  -> modules/<module>/design.md
  -> modules/<module>/testing.md
  -> modules/<module>/bdd/（如有）
  -> modules/<module>/verification/（如有）
  -> process/roadmap.md
```

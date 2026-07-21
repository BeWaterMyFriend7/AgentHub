# 模块文档索引

AgentHub 最终只交付一个应用，内部采用模块化单体。系统级文档描述整体目标、模块关系和跨模块决策；本目录按业务模块纵向组织需求、设计、测试与验证证据。

## 模块划分

| 模块 | 目标 | 主要内容 |
| --- | --- | --- |
| [`agents/`](./agents/README.md) | 建立所有 Agent 接入的统一入口 | Agent 类型、安装、Profile、Adapter 注册和能力矩阵 |
| [`sessions/`](./sessions/README.md) | 可靠观察并精确恢复内部会话 | 会话发现、状态、待处理、规划透传和精确打开 |
| [`capabilities/`](./capabilities/README.md) | 统一表达可复用能力 | Skill、MCP Server、Agent 插件的发现、来源、安装和原生加载状态 |
| [`operations/`](./operations/README.md) | 安全执行会改变外部状态的操作 | 预检、共享、卸载、来源删除、备份、回滚和审计 |

依赖方向保持为：`sessions` 和 `capabilities` 依赖 `agents` 提供的接入契约；需要改变文件系统或 Agent 原生配置时委托 `operations`。`operations` 可以读取能力所有权与 Agent 能力信息，但不反向定义业务对象。

## 每个模块的文档

- `requirements.md`：从总 PRD 派生的模块需求与验收边界；不得覆盖或改变总 PRD。
- `design.md`：模块内部模型、接口、流程以及与其他模块的依赖。
- `testing.md`：单元、契约、集成、API、UI 和平台测试策略。
- `bdd/`：使用中文 Gherkin 描述外部可观察的业务行为。
- `verification/`：按 `YYYY-MM-DD-topic.md` 保存某次真实验证的范围、环境、命令、结果和缺口。
- `references/`：历史来源或研究材料，不作为当前需求事实来源。

## BDD 编写规则

1. 每个场景只验证一个核心行为。
2. 使用业务语言，不引用类名、数据库表、内部函数或具体实现步骤。
3. 结果必须能通过 UI、API、文件系统或 Agent 原生状态观察。
4. 未确认的需求留在总 PRD 或模块需求的待确认部分，不提前写入 BDD。
5. 业务规则变化时，同时更新总 PRD、模块需求和对应 Feature。
6. Feature 使用 UTF-8、中文 Gherkin 和稳定的英文文件名。

## 公共测试底线

各模块的 API 测试都应覆盖响应模型、业务错误和授权失败；涉及修改或共享状态的接口还应覆盖并发与幂等行为。真实 Agent 或文件系统验证必须使用受控夹具，并把证据保存到对应模块的 `verification/`。

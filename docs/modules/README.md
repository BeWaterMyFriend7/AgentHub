# 模块文档索引

AgentHub 只交付一个应用，内部采用模块化单体。每个模块完整维护自己的需求、设计、测试策略和真实验证证据；系统级关系见 [`../architecture/architecture.md`](../architecture/architecture.md)。

## 模块划分

| 模块 | 目标 | 主要内容 |
| --- | --- | --- |
| [`agents/`](./agents/README.md) | 建立所有 Agent 接入的统一入口 | Agent 类型、安装、Profile、Adapter 注册和能力矩阵 |
| [`sessions/`](./sessions/README.md) | 可靠观察并精确恢复内部会话 | 会话发现、运行状态、系统关注、用户跟进标记和精确打开 |
| [`workflows/`](./workflows/README.md) | 顺序执行并跟踪跨项目任务 | 任务队列、自动推进、暂停策略、执行状态和会话定位 |
| [`capabilities/`](./capabilities/README.md) | 统一表达可复用能力 | Skill、MCP Server、Agent 插件的发现、来源、安装和原生加载状态 |
| [`operations/`](./operations/README.md) | 安全执行改变外部状态的操作 | 预检、共享、卸载、来源删除、备份、回滚和审计 |

依赖方向保持为：`sessions` 和 `capabilities` 依赖 `agents`；`workflows` 依赖 `agents` 和 `sessions`；改变文件系统或 Agent 原生能力配置时委托 `operations`。模块之间通过稳定 Interface 协作，不复制对方的业务规则。

## 模块文档

- `README.md`：模块目标、职责和文档入口。
- `requirements.md`：模块业务范围、规则、产品边界和验收条件，是该模块需求事实来源。
- `design.md`：模块内部模型、Interface、流程以及与其他模块的依赖。
- `testing.md`：单元、契约、集成、API、UI 和平台测试策略。
- `bdd/`：可选；使用中文 Gherkin 描述复杂且稳定的外部可观察行为，不保存测试结果。
- `verification/`：只保存真实运行证据，按 `YYYY-MM-DD-topic.md` 记录环境、操作、结果和缺口。
- `references/`：可选；保存历史来源或研究材料，不作为当前需求或设计事实来源。

## BDD 使用规则

1. 只有状态转换复杂、风险较高或需要业务示例澄清时才创建 Feature。
2. 每个场景只验证一个核心行为，使用业务语言，不引用类名、数据库表或内部函数。
3. 结果必须能通过 UI、HTTP Interface、文件系统或 Agent 原生状态观察。
4. 未确认需求留在 `requirements.md` 的待确认部分，不提前写入 BDD。
5. 业务规则变化时同步更新所属模块的需求与对应 Feature。
6. Feature 使用 UTF-8、中文 Gherkin 和稳定的英文文件名。

## Verification 使用规则

真实验证记录说明“某项能力在某个明确环境中是否实际成立”，不能由自动化测试报告或代码存在代替。记录至少包含操作系统、Agent/依赖版本、验证对象、操作步骤、可观察结果、失败项和最终支持等级。没有真实验证证据时，不创建空目录或占位记录。

## 公共测试底线

各模块的 HTTP Interface 测试覆盖响应模型、业务错误和授权失败；涉及修改或共享状态的入口还覆盖并发与幂等。真实 Agent 或文件系统验证使用受控夹具，并将证据保存到主要责任模块的 `verification/`，其他模块只引用。

# AgentHub 文档索引

文档采用“全局文档 + 模块纵向文档”的组织方式。全局文档维护唯一产品口径、系统关系和跨模块决策；每个模块集中维护自己的需求、设计、BDD、测试策略与验证证据。

## 顶层目录

| 目录 | 回答的问题 | 主要文档 |
| --- | --- | --- |
| `prd/` | 为什么做、为谁做、整体做什么 | [`agenthub-v1.md`](./prd/agenthub-v1.md)，唯一当前总 PRD |
| `architecture/` | 系统当前是什么样、模块怎样协作、为什么这样决策 | [`overview.md`](./architecture/overview.md)、[`design.md`](./architecture/design.md)、[`adr/`](./architecture/adr/) |
| `modules/` | 某个模块具体做什么、如何实现和怎样验证 | [`agents`](./modules/agents/README.md)、[`sessions`](./modules/sessions/README.md)、[`capabilities`](./modules/capabilities/README.md)、[`operations`](./modules/operations/README.md) |
| `process/` | 下一步做什么、当前待办、已经学到什么 | `roadmap.md`、`todo.md`、`learnings.md` |
| `guides/` | 如何操作、开发和维护 | [`README.md`](./guides/README.md)；当前暂无可执行的能力管理手册 |
| `prototypes/` | 非生产 UI 和技术实验 | `agent-hub-v1.md`、`agent_hub_prototype_v3.html` |

## 文档职责

- 总 PRD 是当前需求的唯一事实来源；模块 `requirements.md` 只做归属明确的细化。
- `architecture/overview.md` 描述已经存在的当前结构，持续与代码同步。
- `architecture/design.md` 描述模块化单体的系统级边界、依赖和公共基础设施。
- 模块 `design.md` 描述该模块内部模型、接口和流程。
- ADR 只记录重要、难以逆转且存在真实取舍的决策；变化时新增 ADR 并标记旧 ADR 被取代。
- BDD 使用业务语言描述外部可观察行为；测试策略说明如何覆盖；`verification/` 保存某次真实运行的证据。
- `process/roadmap.md` 保存阶段规划，`todo.md` 保存当前工作，`learnings.md` 按日期记录经验。
- 原型仅用于参考，不得被生产代码依赖。
- 历史实现只通过 Git 和模块 `references/` 追溯，不在 `src/` 或 `guides/` 中保留可运行的旧应用。

## 推荐阅读顺序

```text
prd/agenthub-v1.md
  -> architecture/design.md
  -> modules/README.md
  -> modules/<module>/requirements.md
  -> modules/<module>/design.md
  -> modules/<module>/bdd/ 与 testing.md
  -> modules/<module>/verification/
  -> process/roadmap.md
```

# AgentHub 文档索引

文档按产品需求、工程方案、质量验证和项目过程组织。目录保持精简；只有内容量确实需要独立文件时才继续拆分。

## 目录

| 目录 | 回答的问题 | 主要文档 |
| --- | --- | --- |
| `prd/` | 为什么做、为谁做、做什么 | `agenthub-v1.md`（唯一当前总 PRD）及历史/专题来源 |
| `architecture/` | 当前系统是什么样、准备如何实现、为什么这样决策 | `overview.md`、`design.md`、`adr/` |
| `quality/` | 业务怎样验收、技术怎样测试、某次验证结果如何 | `bdd/`、`testing.md`、`verification/` |
| `process/` | 下一步做什么、当前待办、已经学到什么 | `roadmap.md`、`todo.md`、`learnings.md` |
| `guides/` | 如何操作、开发和维护 | `skill-bridge-operations.md` |
| `prototypes/` | 非生产 UI 和技术实验 | `agent_hub_prototype_v3.html` |

## 文档职责

- PRD 描述产品目标、范围和业务规则。
- `prd/agenthub-v1.md` 是当前需求的唯一事实来源；其余 PRD 文件必须明确标记为历史来源或已并入总 PRD。
- `architecture/overview.md` 描述已经存在的当前架构，是持续更新的现状文档。
- `architecture/design.md` 描述当前准备采用的统一技术方案，需求稳定后更新，实现完成后与现状对齐。
- ADR 只记录重要、难以逆转且存在真实取舍的技术决策；决策变化时新增 ADR 并标记旧 ADR 被取代。
- BDD 使用业务语言描述外部可观察的验收行为。
- `quality/testing.md` 说明单元、契约、集成、API、UI 和平台测试策略。
- `quality/verification/` 保存某次真实验证运行的证据。
- `process/roadmap.md` 保存阶段规划，`todo.md` 保存当前工作，`learnings.md` 按日期记录经验。
- 原型仅用于参考，不得被生产代码依赖。

## 推荐阅读顺序

```text
prd/agenthub-v1.md
  -> architecture/design.md
  -> architecture/adr/
  -> quality/bdd/
  -> quality/testing.md
  -> process/roadmap.md
```

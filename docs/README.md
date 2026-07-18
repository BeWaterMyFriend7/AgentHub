# AgentHub 文档索引

本目录将需求意图、架构决策、验证证据和历史记录分开保存，避免所有内容都堆积在一份不断改写的设计文档中。

| 目录 | 用途 | 主要文档 |
| --- | --- | --- |
| `requirements/` | 用户需要什么、哪些内容属于范围 | `agent-session-hub-v0.2.md`、`skill-management-v1.0.md`、`capability-management.md` |
| `architecture/` | 当前系统结构与边界 | `overview.md` |
| `architecture/adr/` | 需要保留历史脉络的架构决策 | `0001-src-and-docs-layout.md`、`0002-capability-adapter-boundary.md` |
| `testing/` | 测试策略、验收规则和验证证据 | `strategy.md`、`verification/README.md` |
| `prototypes/` | 非生产 UI 和技术实验 | `agent_hub_prototype_v3.html` |
| `guides/` | 运维和开发操作指南 | `skill-bridge-operations.md` |
| `planning/` | 路线图与可执行工作 | `TODO.md` |
| `learnings/` | 可能影响后续决策的经验记录 | `README.md` |

需求文档描述期望行为；架构文档描述当前方案；ADR 解释重要选择及原因；测试文档说明如何验证结论；原型仅用于参考，不得被生产代码依赖。


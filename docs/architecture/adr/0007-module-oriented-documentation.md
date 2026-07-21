---
status: accepted
date: 2026-07-22
---

# 采用全局文档与模块纵向文档

AgentHub 最终是一个模块化单体，但 Agents、Sessions、Capabilities、Operations 的需求、设计、测试重点和验证证据差异明显。继续把所有 BDD、测试策略和验证记录集中放在 `quality/`，会使一个模块的规则分散在多个顶层目录中，也不利于后续逐模块完善。

因此保留全局 `prd/` 和 `architecture/`：总 PRD 维护唯一产品事实，系统级架构描述模块关系，ADR 记录跨模块或难以逆转的决策。新增 `modules/`，每个模块纵向维护 `requirements.md`、`design.md`、`testing.md`、`bdd/` 和 `verification/`；历史来源可放在模块 `references/`。删除顶层 `quality/`，原有 BDD、测试策略和验证约定迁入所属模块。

模块需求不能成为第二份总 PRD，模块设计也不能重复系统级架构。公共规则优先放在总 PRD、系统设计或 `modules/README.md`，再由模块文档引用。目录只在已有内容或明确用途时创建，避免为了形式产生多层空目录。

本决策取代 ADR-0006 中关于 `quality/` 的目录安排，同时保留其“目录保持精简”和将路线图、待办、经验收敛到 `process/` 的原则。

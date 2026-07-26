---
status: accepted
date: 2026-07-26
---

# 由模块拥有需求并收敛系统架构文档

AgentHub 的全局 PRD、模块需求、架构现状和目标设计之间存在重复。同一业务规则需要在多个位置同步，增加了冲突和遗漏风险；空的 BDD、Verification 目录也容易让文档结构先于真实内容增长。

因此删除顶层 `prd/`，由各模块的 `requirements.md` 维护所属业务需求和验收条件。`docs/README.md` 只维护产品定位、整体范围、模块地图和阅读入口，不重复模块规则。跨模块需求必须指定主要责任模块，其他模块通过链接引用。

系统现状和目标设计合并到 `architecture/architecture.md`，避免两份文档长期失去同步；`architecture/adr/` 继续保存重要且难以逆转的决策。每个模块按实际需要维护 `README.md`、`requirements.md`、`design.md` 和 `testing.md`，复杂稳定的业务场景才建立 `bdd/`，产生真实 Agent、平台或文件系统证据后才建立 `verification/`，历史方案和调研材料放入可选的 `references/`。

本决策取代 ADR-0007 关于保留顶层总 PRD 的安排，继续保留模块纵向组织、精简目录和历史 ADR 不删除的原则。

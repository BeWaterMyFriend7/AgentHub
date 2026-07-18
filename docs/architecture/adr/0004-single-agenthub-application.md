---
status: accepted
date: 2026-07-18
---

# 最终只交付一个 AgentHub 应用

会话聚合和 SkillBridge 原本可以保持两个本地服务，但这会重复 Agent 配置、数据库、审计、UI 和安装流程。最终只交付一个 AgentHub 应用，SkillBridge 的成熟领域逻辑作为 Skill 子系统合并，MCP 和插件也在相同应用中通过独立模块和 Adapter 接入。

---
status: accepted
date: 2026-07-18
---

# 通过平台适配器实现跨系统能力目录共享

V1 必须兼容 Windows、macOS、Linux，且 Skill、目录型 MCP 和 Agent 插件都需要引用同一物理来源。系统采用统一文件链接契约，Windows 使用 NTFS Junction，macOS/Linux 使用 Symbolic Link；平台链接只负责内容分发，Agent 原生注册和加载验证仍由 Agent Adapter 负责。

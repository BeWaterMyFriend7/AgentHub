# Agents 模块需求

本文是 Agents 模块需求事实来源。

## 目标

为 Codex、Claude Code、OpenCode 及后续 Agent 建立一致、可验证、可扩展的接入入口，避免会话、Skill、MCP 和插件各自维护一套 Agent 配置。

## 范围

- 识别 Agent 产品类型和本机安装实例。
- 创建、编辑、启用、停用并验证 `AgentProfile`。
- 保存 Adapter 所需的 API 端点、Hook、数据位置、能力目录、原生配置位置和 CLI 恢复方式。
- 展示最近连接状态、失败原因和各能力支持等级。
- 注册 Agent Adapter，并向其他模块提供稳定的 Agent 身份和能力声明。

## 业务规则

- Agent 类型、Agent 安装和 AgentHub Profile 是不同对象，不得仅用显示名称合并。
- 停用 Profile 只停止 AgentHub 发现和操作，不删除 Agent 文件、配置或能力。
- 每项能力必须明确声明“支持、不支持或尚未验证”，不能仅因代码路径存在就标记为支持。
- 会话观察、任务执行与 Skill、MCP、插件支持状态分别展示，不能互相推导。
- Adapter 的平台或版本限制必须对用户可见。
- 一个 Agent 接入只有通过对应真实验证，才能从实验性提升为完整支持。

## 验收边界

- 至少能够配置并区分同一 Agent 产品的多个安装或 Profile。
- Profile 校验失败时展示可操作的原因，不影响其他 Profile。
- Sessions、Workflows 和 Capabilities 通过稳定 Agent ID 使用配置，不直接读取 UI 表单状态。
- Windows、macOS、Linux 上的路径和可执行文件探测结果可明确区分“未安装”“无权限”和“尚未验证”。

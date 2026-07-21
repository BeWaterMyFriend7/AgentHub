# 项目待办

## 基础建设

- [ ] 引入测试运行器，为当前会话模型建立基线测试。
- [ ] 使用持久化的 Agent Adapter 配置替换纯 Mock 配置。
- [ ] 将 SkillBridge 的成熟领域逻辑合并为 AgentHub 内部 Skill 模块。
- [ ] 建立 Windows、macOS、Linux 平台文件链接适配接口。

## 会话接入

- [ ] 验证 OpenCode 是否能通过稳定 Server/API 列出多个会话、读取状态和 Todo，并按会话 ID 打开。
- [ ] 验证 Codex 是否提供稳定 Thread ID、权限与轮次事件，以及按 Thread 精确恢复能力。
- [ ] 验证 Claude Code Hooks 能否可靠上报权限、输入、停止和失败事件，并按 Session ID 恢复。
- [ ] 定义 Agent Adapter 的会话发现、状态、规划、事件、探测、恢复和接入等级契约。
- [ ] 为统一会话模型增加运行状态、关注状态、状态来源、可信度和恢复方式。
- [ ] 建立完整接入、部分接入、有限接入的验证夹具，确保进程或窗口探测不进入核心会话统计。
- [ ] 至少完成两个 Agent 的多会话独立状态与精确恢复验证，并把证据保存到 `docs/modules/sessions/verification/`。

## 能力管理

- [ ] 从 `src/skill_bridge/` 提取可复用的 Skill 领域逻辑。
- [ ] 定义统一能力清单与审计模型。
- [ ] 区分能力来源、能力安装、共享安装和原生加载状态。
- [ ] 实现普通安装卸载、全局来源删除、恢复备份和永久清除四种操作边界。
- [ ] 为来源删除增加依赖影响分析、独立确认和完整预检。
- [ ] 在 AgentHub UI 中实现 Skill 管理。
- [ ] 调研 Codex、OpenCode、Claude Code 的 MCP 配置格式与生命周期。
- [ ] 定义 MCP 敏感信息安全归一化和健康探测方案。
- [ ] 调研各 Agent 的原生插件 Manifest、Catalog 和安装操作。
- [ ] 先实现插件清单，再开放插件变更操作。
- [ ] 实现插件所有权、共享引用、独占 MCP 和更新冲突处理。

## 模块验证

- [ ] 增加 Adapter 契约测试，以及 Windows Junction、macOS/Linux Symbolic Link 集成测试夹具。
- [ ] 增加回滚及中断操作恢复测试。
- [ ] 增加敏感信息隐藏和破坏性操作确认的 API/UI 测试。
- [ ] 增加来源删除取消、预检失败、部分失败补偿和永久清除 BDD 验证。

各项测试与证据分别归档到对应模块的 `testing.md`、`bdd/` 和 `verification/`；跨模块场景按主要业务责任归档，并在其他模块文档中引用。

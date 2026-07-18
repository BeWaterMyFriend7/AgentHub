# 项目待办

## 基础建设

- [ ] 引入测试运行器，为当前会话模型建立基线测试。
- [ ] 使用持久化的 Agent Adapter 配置替换纯 Mock 配置。
- [ ] 将 SkillBridge 的成熟领域逻辑合并为 AgentHub 内部 Skill 模块。
- [ ] 建立 Windows、macOS、Linux 平台文件链接适配接口。

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

## 质量保障

- [ ] 增加 Adapter 契约测试，以及 Windows Junction、macOS/Linux Symbolic Link 集成测试夹具。
- [ ] 增加回滚及中断操作恢复测试。
- [ ] 增加敏感信息隐藏和破坏性操作确认的 API/UI 测试。
- [ ] 增加来源删除取消、预检失败、部分失败补偿和永久清除 BDD 验证。

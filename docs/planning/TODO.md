# 项目待办

## 基础建设

- [ ] 引入测试运行器，为当前会话模型建立基线测试。
- [ ] 使用持久化的 Agent Adapter 配置替换纯 Mock 配置。
- [ ] 决定将 SkillBridge 合并为内部模块，还是保留为独立本地服务。

## 能力管理

- [ ] 从 `src/skill_bridge/` 提取可复用的 Skill 领域逻辑。
- [ ] 定义统一能力清单与审计模型。
- [ ] 在 AgentHub UI 中实现 Skill 管理。
- [ ] 调研 Codex、OpenCode、Claude Code 的 MCP 配置格式与生命周期。
- [ ] 定义 MCP 敏感信息安全归一化和健康探测方案。
- [ ] 调研各 Agent 的原生插件 Manifest、Catalog 和安装操作。
- [ ] 先实现插件清单，再开放插件变更操作。

## 质量保障

- [ ] 增加 Adapter 契约测试和 Windows Junction 集成测试夹具。
- [ ] 增加回滚及中断操作恢复测试。
- [ ] 增加敏感信息隐藏和破坏性操作确认的 API/UI 测试。


# 架构总览

## 当前运行结构

```text
浏览器 UI
  -> FastAPI 应用工厂（src/agent_hub/main.py）
  -> 运行时组合（src/agent_hub/bootstrap.py）
       ├── agents/AgentRegistry
       ├── sessions/SessionHub
            ├── sessions/adapters/MockSessionAdapter
            └── sessions/SessionEventLog
       └── demo/DemoSessionController（仅演示状态推进）
```

当前代码已经形成模块化单体骨架：`agents` 与 `sessions` 进入应用运行时；`capabilities` 提供只读 Skill 发现与统一能力模型；`operations` 提供共享安装的预检、确认、备份、目录链接、验证、回滚与审计；`platform` 隐藏 Windows Junction 和 macOS/Linux Symbolic Link 差异。旧的会话 `models.py`、`service.py`、`repository.py`、`seed.py` 和 `adapters/` 暂时作为迁移兼容层。

核心模型和新 API 统一使用 `agent_id`、`agent_name`；`tool_id` 等旧术语只保留在旧 Python 访问别名和 `/api/tools` 兼容边界中。Demo 状态推进由 `demo` 控制器编排，不属于生产 Session Adapter 契约。

历史 SkillBridge 已完成本轮领域逻辑提取，其独立应用源码已从 `src/` 移除，迁移结论记录在 [`../modules/capabilities/references/skill-bridge-migration.md`](../modules/capabilities/references/skill-bridge-migration.md)。Capabilities 与 Operations 暂未接入 HTTP API/UI，也尚未实现 MCP、插件、来源删除和持久化审计；这些功能继续在同一个 AgentHub 应用内迭代，不恢复独立 SkillBridge 应用。

## 目标模块化单体

```text
AgentHub 应用
├── agents        Agent 身份、安装、Profile 与 Adapter 注册
├── sessions      会话发现、状态、待处理与精确恢复
├── capabilities  Skill、MCP、插件的统一清单与类型策略
└── operations    预检、共享、卸载、备份、回滚与审计
```

公共基础设施包括 API/UI、Repository、事件更新、平台链接 Adapter 和本地安全边界。模块文档见 [`../modules/`](../modules/README.md)。

UI 只消费归一化读模型，不直接解释 Agent 原生配置或执行平台命令。目录链接只建立内容引用；链接完成后仍由 Agent Adapter 执行原生配置、刷新或注册，并确认目标 Agent 已加载能力。

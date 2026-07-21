# 架构总览

## 当前运行结构

```text
浏览器 UI
  -> FastAPI 路由（src/agent_hub/main.py）
  -> 会话应用服务
  -> 统一模型与 Repository
  -> Mock Agent Adapter
```

当前接近生产结构的代码只实现了基于 Mock Adapter 的会话聚合。`src/skill_bridge/` 是待合并的 Skill 参考子系统；最终只运行一个 AgentHub 应用。

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

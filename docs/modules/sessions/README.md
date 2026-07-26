# Sessions 模块

本模块负责聚合 Agent 内部会话，展示可信状态、系统关注原因和用户跟进标记，并按稳定原生会话标识精确恢复目标会话。它不负责任务排队或自动发送后续任务。

- [需求](./requirements.md)
- [设计](./design.md)
- [测试策略](./testing.md)
- [BDD 场景](./bdd/)
- [模块拆分历史记录](./references/2026-07-22-agents-sessions-module-split.md)

真实 Agent 验证证据产生后再创建 `verification/`。

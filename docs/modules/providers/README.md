# Providers 模块

Providers 模块统一管理 Codex 与 Claude Code 使用的模型厂商、模型目录、默认路由、会话固定路由和本地协议网关。

- [`requirements.md`](./requirements.md)：首版范围、路由语义和安全约束。
- [`design.md`](./design.md)：模块边界、数据模型、客户端接管和协议矩阵。
- [`testing.md`](./testing.md)：隔离测试、假上游和真实配置保护要求。
- [`user-guide.md`](./user-guide.md)：用户操作流程与回滚方式。

旧 `model_switch` Flask 服务属于迁移期兼容实现，不再承载新的 Provider 功能。

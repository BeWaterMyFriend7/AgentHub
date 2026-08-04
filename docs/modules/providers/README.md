# Providers 模块

Providers 模块统一管理 Codex 与 Claude Code 使用的模型厂商、模型目录、默认路由、会话固定路由和本地协议网关。

- [`requirements.md`](./requirements.md)：Provider 生命周期、凭据、模型目录、路由、协议网关、客户端接管、暂停状态（已记录暂不实现）与安全约束。
- [`design.md`](./design.md)：模块边界、持久化、状态模型、客户端接管、协议矩阵与关键流程。
- [`testing.md`](./testing.md)：隔离测试、假上游和真实配置保护要求。
- [`user-guide.md`](./user-guide.md)：用户操作流程与回滚方式。

旧 `model_switch` Flask 服务属于迁移期兼容实现，不再承载新的 Provider 功能。

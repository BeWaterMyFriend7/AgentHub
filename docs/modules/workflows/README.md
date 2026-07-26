# Workflows 模块

本模块负责把一个或多个项目中的任务组成有序队列，在前一任务可靠完成后推进下一任务，并保存每次执行对应的原生会话定位。

- [需求](./requirements.md)
- [设计](./design.md)
- [测试策略](./testing.md)

复杂业务场景稳定后再创建 `bdd/`；完成真实 Agent 串行执行验证后再创建 `verification/`。

# Providers 模块测试

## 自动化边界

- Provider Registry：CRUD、凭据脱敏、默认路由与模型校验。
- 客户端接管：保留无关字段、原始字节恢复、外部修改检测、真实 Home 禁写保护。
- 会话路由：会话优先级、显式 `provider/model`、默认路由和 Claude metadata 会话识别。
- Gateway：使用 `httpx.MockTransport` 验证六种客户端/上游协议组合、结束原因和工具调用，不访问真实模型服务。
- Claude Code Session Adapter：临时 JSONL 会话发现和 `--resume` 参数。

## 配置保护

遗留 `tests/test_model_switch/` 的 Flask 服务改为在每次请求时解析 Home，避免模块导入时捕获真实路径。运行该测试目录时必须在前后校验真实 `~/.codex/config.toml` SHA-256 完全一致。

真实端到端验证必须由用户准备测试 Provider 凭据，并显式启用客户端接管；自动化测试不能把真实 API Key 输出到终端或日志。

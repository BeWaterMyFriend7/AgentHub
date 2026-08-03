# Providers 模块需求

## 首版范围

1. 在 AgentHub FastAPI 主应用内管理 Provider，不要求用户启动第二个 Flask 服务。
2. 同时支持 Codex 和 Claude Code 两个客户端。
3. 支持三类上游协议：OpenAI Responses、OpenAI-compatible Chat Completions、Anthropic Messages。
4. 每个客户端拥有独立默认 `provider/model` 路由。
5. 新会话跟随默认路由；老会话可固定路由或持续跟随默认。无法可靠识别历史路由时必须标为未确认并失败关闭，不能静默套用新默认。
6. 同协议流式透传；跨协议转换文本和函数工具调用，并输出目标客户端可读取的 JSON 或 SSE。

## 安全规则

- Provider 配置只保存环境变量名称，不保存 API Key 值。
- 客户端接管必须由用户从 UI 显式触发。
- 修改前备份原始字节并记录注入后 SHA-256。
- 配置被外部修改后禁止自动覆盖或恢复。
- 测试必须注入临时配置路径；未显式授权时禁止写入真实 Home。
- 不修改 Codex `state_*.sqlite`、rollout JSONL 或 Claude Code 会话 JSONL。

## 路由优先级

1. 已记录的会话固定路由。
2. 请求模型中的显式 `provider/model`。
3. 客户端默认路由。

Provider 不可用或凭据缺失时返回明确错误；首版不启用静默 fallback。

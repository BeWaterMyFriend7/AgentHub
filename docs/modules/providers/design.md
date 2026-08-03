# Providers 模块设计

## 公共边界

`ProviderControl` 是管理面和会话模块使用的公共 Interface：

- 保存、列出和删除 Provider；
- 设置 Codex/Claude Code 默认路由；
- 解析请求路由；
- 固定或释放会话路由；
- 返回脱敏后的 Provider 与路由视图。

`ProviderGateway` 是数据面 Interface，负责上游认证替换、协议适配、错误转发和 SSE。

## 持久化

- `~/.agenthub/providers.json`：Provider Registry 和两个客户端的默认路由。
- `~/.agenthub/session-routes.json`：会话路由快照。
- `~/.agenthub/client-integrations/`：客户端接管 journal。
- `~/.agenthub/backups/`：接管前的原始配置字节。

Provider 只保存 `secret_env`。运行时从环境变量读取真实凭据，并根据目标协议生成 `Authorization: Bearer` 或 `x-api-key`。

## 客户端接管

Codex 用户级 `~/.codex/config.toml` 注入：

```toml
model_provider = "openai"
openai_base_url = "http://127.0.0.1:17860/v1"
model = "<默认模型>"
```

Claude Code 用户级 `~/.claude/settings.json` 的 `env` 注入：

```json
{
  "ANTHROPIC_BASE_URL": "http://127.0.0.1:17860",
  "ANTHROPIC_AUTH_TOKEN": "agenthub-local",
  "ANTHROPIC_MODEL": "<默认模型>"
}
```

本地 token 只是客户端到 loopback 网关的占位认证，不会转发到上游。

## 协议矩阵

| 客户端 | 上游 Responses | 上游 OpenAI-compatible | 上游 Anthropic |
| --- | --- | --- | --- |
| Codex Responses | 流式透传 | 转 Chat Completions，再转回 Responses | 转 Messages，再转回 Responses |
| Claude Code Messages | 转 Responses，再转回 Messages | 转 Chat Completions，再转回 Messages | 流式透传 |

首版跨协议 SSE 会先完整读取上游流，再重放为目标协议 SSE；同协议保持逐块透传。这个边界优先保证工具调用和结束事件结构正确，高级版本再增加跨协议逐事件低延迟转换。

## 会话识别

- Codex：`x-codex-parent-thread-id`、`session_id` 或 `x-session-id`。
- Claude Code：`x-claude-code-session-id`、`claude-code-session-id`，或 `metadata.user_id` 中的 `_session_` 后缀。

首次看到稳定会话 ID 时记录真实路由。AgentHub 会话页使用同一 native session ID 显示和修改绑定。

会话路由具有三种持久状态：`fixed` 固定到指定 Provider/模型；`follow_default` 持续读取客户端最新默认路由；`unresolved` 表示接管前历史会话的原路由无法可靠确认。`unresolved` 会话在用户明确选择前拒绝代理请求，避免静默切换厂商。

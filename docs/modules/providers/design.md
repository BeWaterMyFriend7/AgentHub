# Providers 模块设计

Providers 模块负责模型厂商的持久化、路由决策与协议网关，同时管理 Codex/Claude Code 客户端配置接管。本文描述当前实现结构；需求层面的产品规则见 [`requirements.md`](./requirements.md)。

## 模块边界

对外暴露两个稳定 Interface：

- `ProviderControl`：管理面与会话模块使用的公共 Interface。负责保存、列出和删除 Provider；设置 Codex/Claude Code 默认路由；固定或释放会话路由；解析请求路由；返回脱敏后的 Provider 与路由视图。
- `ProviderGateway`：数据面 Interface。负责上游认证替换、协议适配、错误转发和 SSE。

依赖方向：`sessions` 只读取 `ProviderControl` 暴露的会话路由视图；`main` 组合两者。持久化仓库（`ProviderRegistry`、`SessionRouteStore`）作为控制面内部实现，不向外部暴露。

## 持久化

- `~/.agenthub/providers.json`：Provider Registry 和两个客户端的默认路由。
- `~/.agenthub/secrets.json`：Provider API Key 的 DPAPI 密文（Windows）；文件不含明文。
- `~/.agenthub/session-routes.json`：会话路由快照。
- `~/.agenthub/client-integrations/`：客户端接管 journal。
- `~/.agenthub/backups/`：接管前的原始配置字节。

Provider 配置只保存 `secret_env` 与 `hidden_models` 等非敏感字段；`SecretStore` 负责密钥密文的读写。运行时凭据解析顺序：本地加密密钥 → 环境变量。网关根据目标协议生成 `Authorization: Bearer` 或 `x-api-key`。

## Provider ID 生成

`ProviderControl.save_provider` 在 `id` 缺失时按显示名称 slug 化生成 ID（中文等无 slug 内容时回退为 `provider`），并基于 Registry 现有 ID 追加 `-2`、`-3` 序号保证唯一；编辑时沿用已有 ID。密钥存储与 ID 生成均在线程锁内完成。

## 密钥存储

`SecretStore` 使用 Windows `CryptProtectData`/`CryptUnprotectData`（DPAPI）加密 API Key，密文 Base64 后写入 `secrets.json`；`protect`/`unprotect` 可注入以便跨平台测试。保存时同步写入，删除 Provider 时同步清除。密钥永不进入 `ProviderView`、注册表文件或日志。

## 模型探测与可见性

- 创建/更新 Provider 后由网关请求 `{base_url}/v1/models`，探测成功则写回模型列表；失败保留原列表并返回 `detection_warning`。
- 显式“重新检测模型”接口对探测失败返回 400。
- 每个 Provider 维护 `hidden_models`；`/v1/models` 与路由选择器排除隐藏模型，精确 ID 请求仍可路由。

## 状态模型

当前 Provider 状态只有 `enabled`（true/false）。需求已记录独立的 `paused` 暂停状态（见 [`requirements.md`](./requirements.md#8-provider-暂停状态需求已记录暂不实现)），本版本不设计、不实现；实现时需扩展 Provider 状态字段并明确暂停与停用的语义差异，同时补充暂停对默认路由、显式路由与会话绑定的影响。

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

本地 token 只是客户端到 loopback 网关的占位认证，不会转发到上游。接管流程：显式触发 → 备份原始字节 → 原子写入注入配置 → 记录注入后 SHA-256；当前文件与 journal 不一致时拒绝覆盖或恢复。

## 协议矩阵

| 客户端 | 上游 Responses | 上游 OpenAI-compatible | 上游 Anthropic |
|--------|----------------|------------------------|----------------|
| Codex Responses | 流式透传 | 转 Chat Completions，再转回 Responses | 转 Messages，再转回 Responses |
| Claude Code Messages | 转 Responses，再转回 Messages | 转 Chat Completions，再转回 Messages | 流式透传 |

首版跨协议 SSE 会先完整读取上游流，再重放为目标协议 SSE；同协议保持逐块透传。这个边界优先保证工具调用和结束事件结构正确，高级版本再增加跨协议逐事件低延迟转换。

## 会话识别

- Codex：`x-codex-parent-thread-id`、`session_id` 或 `x-session-id`。
- Claude Code：`x-claude-code-session-id`、`claude-code-session-id`，或 `metadata.user_id` 中的 `_session_` 后缀。

首次看到稳定会话 ID 时记录真实路由。AgentHub 会话页使用同一 native session ID 显示和修改绑定。

## 会话路由状态

会话路由具有三种持久状态：

| 状态 | 含义 | 请求行为 |
|------|------|----------|
| `fixed` | 固定到指定 Provider/模型 | 始终使用绑定路由 |
| `follow_default` | 持续读取客户端最新默认路由 | 随默认路由变化 |
| `unresolved` | 接管前历史会话的原路由无法可靠确认 | 用户明确选择前拒绝代理请求 |

路由解析优先级：会话固定路由 → 显式 `provider/model` → 客户端默认路由。

## 关键流程

### 请求转发

1. 网关从请求头与请求体提取客户端与会话 ID。
2. `ProviderControl.resolve_route` 按固定路由 → 显式 → 默认解析，未配置默认路由时返回明确错误。
3. 记录观察到的会话路由。
4. 转换器按客户端与上游协议准备请求；网关替换认证头并转发。
5. 同协议流式透传；跨协议读取完整上游流，经规范化中间表示后重放为目标客户端响应。

### 客户端接管

1. UI 显式触发启用接管。
2. 备份原始字节到 `backups/`，原子写入本地网关配置。
3. 记录注入后 SHA-256 到 journal。
4. 检测到外部修改时拒绝自动覆盖或恢复；用户确认后执行恢复。

## 与待确认需求的关系

自动生成 Provider ID、API Key 本地加密保存、模型自动探测与分组可见性已实现，本文对应小节即为其设计；Provider 暂停状态仍为“需求已记录、暂不实现”（见 [`requirements.md`](./requirements.md#8-provider-暂停状态需求已记录暂不实现)）；Skill 管理的发现与共享设计归属 [Capabilities 模块](../capabilities/design.md)。

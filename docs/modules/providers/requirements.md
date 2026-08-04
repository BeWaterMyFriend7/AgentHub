# Providers 模块需求

本文是 Providers 模块需求事实来源。Provider 生命周期、凭据、模型目录、客户端默认路由、会话路由、协议网关与客户端配置接管的产品规则均以此为准；已记录但暂不实现的需求明确标注。

## 概述

为 Codex 与 Claude Code 提供统一的模型厂商管理入口与本地协议网关：用户只维护一份 Provider 配置，即可分别为两个客户端设置默认模型、按会话固定模型，并让客户端通过本地网关访问所选厂商，无需手工修改客户端配置。

### 目标

1. **统一管理**：一个 Provider Registry 同时服务 Codex 与 Claude Code，避免两套客户端配置各自维护厂商信息。
2. **双客户端覆盖**：Codex（Responses 协议）与 Claude Code（Messages 协议）均可配置独立默认路由。
3. **多协议互通**：支持 OpenAI Responses、OpenAI-compatible Chat Completions 与 Anthropic Messages 三类上游协议，跨协议时转换文本与工具调用。
4. **会话级可控**：新会话跟随默认路由，老会话可固定 Provider/模型或持续跟随默认；无法确认的历史路由失败关闭，不静默切换厂商。
5. **安全优先**：API Key 不落盘、不回传、不记日志；客户端接管前备份、可审计、可恢复，外部修改后禁止自动覆盖。

### 需求点总览

| 编号 | 需求点 | 说明 | 详细位置 |
|------|--------|------|----------|
| 1 | Provider 生命周期 | 新增、编辑、删除、启用/停用 | [1. Provider 生命周期管理](#1-provider-生命周期管理) |
| 2 | 凭据与密钥 | 环境变量引用兼容；Windows DPAPI 本地加密保存 | [2. 凭据与密钥](#2-凭据与密钥) |
| 3 | 模型目录 | 自动探测模型；分组展示与可见性开关 | [3. 模型目录](#3-模型目录) |
| 4 | 客户端默认路由 | Codex/Claude Code 独立默认 `provider/model` | [4. 客户端默认路由](#4-客户端默认路由) |
| 5 | 会话路由 | 固定、跟随默认、未确认三种状态 | [5. 会话路由](#5-会话路由) |
| 6 | 协议网关 | 三类上游协议与跨协议转换 | [6. 协议网关](#6-协议网关) |
| 7 | 客户端配置接管 | 备份、注入、外部修改检测与恢复 | [7. 客户端配置接管](#7-客户端配置接管) |
| 8 | Provider 暂停状态 | 临时关闭任一 Provider（含官方）；需求已记录、暂不实现 | [8. Provider 暂停状态](#8-provider-暂停状态需求已记录暂不实现) |
| 9 | 安全规则 | 凭据、配置与真实客户端目录保护 | [9. 安全规则](#9-安全规则) |
| 10 | 验收标准 | 功能、安全与 UI 验收 | [10. 验收标准](#10-验收标准) |

---

## 1. Provider 生命周期管理

### 1.1 配置字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `id` | string | 否 | 自动生成 | Provider 唯一标识，小写字母/数字/`-_`；未填写时按显示名称自动生成并保证唯一 |
| `name` | string | 是 | - | 显示名称，1-120 字符 |
| `protocol` | enum | 是 | - | `openai_responses` / `openai_compatible` / `anthropic` |
| `base_url` | string | 是 | - | http/https 地址，保存时去除末尾 `/` |
| `secret_env` | string | 否 | "" | API Key 环境变量名（兼容旧配置）；留空表示无需凭据 |
| `api_key` | string | 否 | - | API Key 值，仅写入时使用；保存后不回传、不落盘明文 |
| `models` | list[string] | 否 | [] | 声明的模型列表，保存时去重 |
| `hidden_models` | list[string] | 否 | [] | 在模型目录与选择器中隐藏的模型；仍可按精确 ID 调用 |
| `enabled` | boolean | 是 | true | 是否启用该 Provider |

### 1.2 规则

- 新增、编辑、删除均在 AgentHub 主应用内完成，不需要第二个服务。
- 创建时不要求填写 `id`；系统按名称生成稳定 ID，重名自动追加序号，编辑后 ID 保持不变。
- `enabled=false` 只停止该 Provider 参与路由和请求，不删除配置。
- 删除 Provider 时同步清理引用它的默认路由；已绑定该 Provider 的会话路由按[5. 会话路由](#5-会话路由)处理。
- 删除需用户确认，并提示默认路由失效影响。

---

## 2. 凭据与密钥

- Provider 配置不保存 API Key 明文；支持两种凭据来源：
  - 本地加密保存：新建或编辑时填写的 API Key 使用 Windows 系统级 DPAPI 加密后写入 `secrets.json`，运行时按需解密。
  - 环境变量引用（兼容）：`secret_env` 指向的环境变量作为回退来源。
- 本地加密密钥优先于环境变量。
- 表单密钥默认隐藏，点击“显示”临时可见；保存后不可回显，只能删除 Provider 后重新添加或直接覆盖新密钥。
- API 响应、日志与 UI 永不回传密钥值。
- 删除 Provider 时同步删除其本地加密密钥。
- 两个来源都缺失时按凭据缺失处理并返回明确错误。

---

## 3. 模型目录

- 新建或编辑 Provider 时自动请求 `{base_url}/v1/models` 探测模型并写入模型列表；探测失败仍保存 Provider，并返回检测失败提示。
- 提供“重新检测模型”动作，手动刷新模型列表。
- “测试连接”请求 `{base_url}/v1/models` 验证凭据与可达性并返回发现数量。
- 模型按 Provider 分组展示，支持折叠、全部开启/全部关闭和单模型可见性开关。
- 隐藏模型不出现在模型目录、默认路由与选择器中，但仍可按精确 ID 直接调用。

---

## 4. 客户端默认路由

- Codex 与 Claude Code 各自拥有独立默认 `provider/model`。
- 保存默认路由时校验 Provider 存在且模型在该 Provider 声明范围内。
- 新会话跟随客户端默认路由；已有会话绑定优先于默认路由。

---

## 5. 会话路由

路由解析优先级：

1. 已记录的会话固定路由（`fixed`）。
2. 请求模型中的显式 `provider/model`。
3. 客户端默认路由。

会话路由具有三种持久状态：

| 状态 | 含义 | 请求行为 |
|------|------|----------|
| `fixed` | 会话固定到指定 Provider/模型 | 始终使用绑定路由 |
| `follow_default` | 持续读取客户端最新默认路由 | 随默认路由变化 |
| `unresolved` | 接管前历史会话的原路由无法确认 | 用户明确选择前失败关闭，不静默切换厂商 |

- 首次通过网关看到稳定会话 ID 时记录实际路由。
- 用户在 UI 可将会话固定到 Provider/模型，或设为跟随默认。

---

## 6. 协议网关

| 客户端 | 上游 Responses | 上游 OpenAI-compatible | 上游 Anthropic |
|--------|----------------|------------------------|----------------|
| Codex（Responses） | 同协议流式透传 | 转 Chat Completions，再转回 Responses | 转 Messages，再转回 Responses |
| Claude Code（Messages） | 转 Responses，再转回 Messages | 转 Chat Completions，再转回 Messages | 同协议流式透传 |

- 同协议保持逐块透传；跨协议先读取完整上游流，转换后重放为目标客户端 SSE 或 JSON。
- 网关替换上游认证头：OpenAI 系使用 `Authorization: Bearer`，Anthropic 使用 `x-api-key`。
- 上游错误按原状态码透传；请求体非 JSON 或路由无效时返回明确 4xx。
- 首版不启用 Provider 自动 fallback；Provider 不可用或凭据缺失时返回明确错误。

---

## 7. 客户端配置接管

- 接管必须由用户从 UI 显式触发。
- Codex：向 `~/.codex/config.toml` 注入 `model_provider = "openai"`、`openai_base_url = <本地网关>/v1`、`model = <默认模型>`。
- Claude Code：向 `~/.claude/settings.json` 的 `env` 注入 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_MODEL`。
- 修改前备份原始字节，记录注入后 SHA-256。
- 外部修改检测：当前文件与注入后 SHA-256 不一致时，禁止自动覆盖或恢复。
- “恢复原配置”只恢复备份中的原始字节，并删除接管 journal。
- 本地 token 仅用于客户端到 loopback 网关的占位认证，不会转发到上游。

---

## 8. Provider 暂停状态（需求已记录，暂不实现）

> 状态：需求已记录。本版本不实现，不进入验收基线；设计在确认后补充到 `design.md`。

- 为 Provider 增加独立的 `paused` 暂停状态，与 `enabled=false` 区分：
  - `enabled=false` 表示未启用/停用，等同移除出可选项。
  - `paused` 表示临时关闭，保留全部配置、凭据引用、模型列表与路由记录，可随时恢复。
- 暂停可作用于任意 Provider，包括官方/默认 Provider；暂停期间该 Provider 不参与默认路由候选、显式路由解析与请求转发。
- 已绑定被暂停 Provider 的会话与默认路由不得静默 fallback 到其他厂商；请求返回明确错误，提示“Provider 已暂停”。
- UI 提供“暂停/恢复”动作与暂停状态标识；暂停不影响 Provider 的编辑、删除与重新检测能力。
- 验收（实现时补充）：暂停后新请求明确失败且不切换厂商；恢复后无需重新配置即可路由；暂停状态持久化并在重启后保持。

---

## 9. 安全规则

- Provider 配置只保存环境变量名称，不保存 API Key 值。
- API Key 可选使用 Windows DPAPI 本地加密保存；文件、响应与日志均不出现明文。
- 客户端接管必须由用户从 UI 显式触发。
- 修改前备份原始字节并记录注入后 SHA-256。
- 配置被外部修改后禁止自动覆盖或恢复。
- 测试必须注入临时配置路径；未显式授权时禁止写入真实 Home。
- 不修改 Codex `state_*.sqlite`、rollout JSONL 或 Claude Code 会话 JSONL。
- API Key 不得输出到终端、日志或浏览器响应。

---

## 10. 验收标准

| 验收项 | 验收标准 |
|--------|----------|
| Provider CRUD | 新增、编辑、删除、启用/停用均通过 HTTP Interface 可用，业务错误与授权失败有明确响应 |
| 自动 ID | 不传 `id` 可创建，按名称生成稳定唯一 ID；编辑保持 ID 不变 |
| 密钥安全 | API Key 加密落盘、不回传、保存后不可回显；删除 Provider 清除密钥；外部无法读取明文 |
| 模型探测 | 创建/编辑自动探测模型；“重新检测模型”可刷新；探测失败不阻断保存并给出提示 |
| 模型可见性 | 隐藏模型不出现在 `/v1/models` 与选择器；恢复可见后重新出现 |
| 路由解析 | 固定路由 > 显式 `provider/model` > 默认路由；`unresolved` 会话失败关闭 |
| 协议矩阵 | 六种客户端×上游组合通过 MockTransport 验证，含流式与工具调用 |
| 配置保护 | 接管前后真实 `~/.codex/config.toml` SHA-256 一致；外部修改检测触发时拒绝覆盖 |
| 凭据安全 | providers.json、API 响应与日志中不含密钥值 |
| 幂等与并发 | 修改共享状态的 HTTP 入口覆盖并发与重复调用 |

---

## 变更记录

- 2026-08-05：Provider ID 自动生成、API Key 本地加密保存（Windows DPAPI）、模型自动探测与分组可见性已实现并纳入验收基线。
- 2026-08-05：Skill 管理已集成到 AgentHub UI，需求与实现归属 [Capabilities 模块](../capabilities/requirements.md)。

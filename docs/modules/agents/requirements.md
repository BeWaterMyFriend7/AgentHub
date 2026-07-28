# Agents 模块需求

本文是 Agents 模块需求事实来源。

## 概述

为 Codex、Claude Code、OpenCode 及后续 Agent 建立一致、可验证、可扩展的接入入口，避免会话、Skill、MCP 和插件各自维护一套 Agent 配置。

### 目标

1. **统一接入**：为所有 Agent 提供统一的配置入口，消除重复配置
2. **自动发现**：自动探测本地已安装的 Agent，减少手动配置工作
3. **可验证性**：提供连接验证和诊断功能，确保配置正确可用
4. **灵活扩展**：支持新 Agent 类型的快速接入，不影响现有配置
5. **安全可靠**：敏感信息通过环境变量管理，不在配置文件中明文存储

### 需求点总览

| 编号 | 需求点 | 说明 | 详细位置 |
|------|--------|------|----------|
| 1 | 业务规则 | Agent 类型、安装和 Profile 的区分，能力声明原则 | [1. 业务规则](#1-业务规则) |
| 2 | 配置字段规格 | 通用字段及各 Agent 特定字段，字段验证规则 | [2. 配置字段规格](#2-配置字段规格) |
| 3 | Profile 管理流程 | 创建、编辑、启用/停用、删除流程 | [3. Profile 管理流程](#3-profile-管理流程) |
| 4 | Agent 自动探测 | 探测范围、可信度、平台特定路径 | [4. Agent 自动探测](#4-agent-自动探测) |
| 5 | 配置验证与诊断 | 验证时机、验证项目、诊断建议 | [5. 配置验证与诊断](#5-配置验证与诊断) |
| 6 | UI 与持久化 | UI 交互规格、配置持久化、安全性要求 | [6. UI 与持久化](#6-ui-与持久化) |
| 7 | 验收标准 | 验收边界、测试用例、回归检查清单 | [7. 验收标准](#7-验收标准) |

---

## 1. 业务规则

- Agent 类型、Agent 安装和 AgentHub Profile 是不同对象，不得仅用显示名称合并。
- 停用 Profile 只停止 AgentHub 发现和操作，不删除 Agent 文件、配置或能力。
- 每项能力必须明确声明"支持、不支持或尚未验证"，不能仅因代码路径存在就标记为支持。
- 会话观察、任务执行与 Skill、MCP、插件支持状态分别展示，不能互相推导。
- Adapter 的平台或版本限制必须对用户可见。
- 一个 Agent 接入只有通过对应真实验证，才能从实验性提升为完整支持。

---

## 2. 配置字段规格

### 2.1 配置字段规格

#### 2.1.1 通用字段

所有 Agent Profile 必须包含以下字段：

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `profile_id` | string | 是 | UUID | Profile 唯一标识，创建时自动生成 |
| `profile_name` | string | 是 | - | 用户友好的显示名称，2-50字符 |
| `agent_type` | enum | 是 | - | Agent 产品类型：`codex`/`claude_code`/`opencode`/`hermes` |
| `adapter_kind` | enum | 是 | - | 接入方式：`codex_desktop`/`opencode_desktop`/`opencode_server`/`claude_code_desktop` 等 |
| `enabled` | boolean | 是 | true | 是否启用此 Profile |
| `created_at` | datetime | 是 | 当前时间 | 创建时间 |
| `updated_at` | datetime | 是 | 当前时间 | 最后修改时间 |
| `installation_id` | string | 否 | null | 关联的自动探测安装 ID |

#### 2.1.2 Codex Desktop 特定字段

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `codex_home` | path | 是 | `~/.codex` | Codex 数据目录，包含 state_*.sqlite |
| `db_file_pattern` | string | 否 | `state_*.sqlite` | 状态数据库文件名模式 |
| `deep_link_scheme` | string | 否 | `codex://` | Desktop 深链 URL Scheme |

#### 2.1.3 OpenCode Desktop 特定字段

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `db_path` | path | 是 | `~/.local/share/opencode/opencode.db` | OpenCode 本地数据库路径 |
| `cli_executable` | path | 否 | `opencode` | CLI 可执行文件路径或命令名 |

#### 2.1.4 OpenCode Server 特定字段

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `server_url` | url | 是 | - | OpenCode Server 地址，如 `http://localhost:8000` |
| `secret_env` | string | 是 | `OPENCODE_SERVER_PASSWORD` | 存储密码的环境变量名 |
| `cli_executable` | path | 否 | `opencode` | CLI 可执行文件路径或命令名 |
| `timeout_seconds` | integer | 否 | 30 | API 请求超时时间（秒），范围 5-300 |
| `verify_ssl` | boolean | 否 | true | 是否验证 SSL 证书 |

#### 2.1.5 Claude Code Desktop 特定字段

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `data_dir` | path | 是 | 平台相关 | Claude Code 数据目录 |
| `db_file_name` | string | 否 | `state.db` | 状态数据库文件名 |

### 2.2 字段验证规则

#### 2.2.1 profile_name
- 长度：2-50 字符
- 允许：字母、数字、空格、中文、`-_()` 等常见符号
- 禁止：纯空格、仅符号
- 唯一性：同一 `agent_type` + `adapter_kind` 组合下不允许重名

#### 2.2.2 路径字段（codex_home / db_path / data_dir）
- 必须是绝对路径或以 `~` 开头的用户目录路径
- 路径存在性检查：**警告但不阻止保存**，允许用户配置尚未启动的 Agent
- 权限检查：如果路径存在，必须具有读取权限
- 错误提示：
  - "路径不存在或无法访问，请检查 Agent 是否已安装"（警告级别）
  - "没有读取权限，请检查文件系统权限"（错误级别）

#### 2.2.3 server_url
- 格式：有效的 HTTP/HTTPS URL
- 端口：1-65535
- 连接性测试：**可选**，用户点击"测试连接"按钮时执行

#### 2.2.4 secret_env
- 格式：有效的环境变量名（字母、数字、下划线，不以数字开头）
- 存在性检查：**警告但不阻止保存**，运行时从环境读取

#### 2.2.5 cli_executable
- 格式：绝对路径或命令名
- 存在性检查：检查文件是否存在或在 PATH 中
- 检查结果为**警告**，不阻止保存
- 错误提示："CLI 工具未找到，精确恢复功能可能不可用"（警告级别）

---

## 3. Profile 管理流程
**原型参考**: [agent-config-prototype.html](../../prototypes/agent-config-prototype.html) - [原型1.2]

### 3.1 创建流程
**原型参考**: [agent-config-prototype.html](../../prototypes/agent-config-prototype.html) - [原型1.2.1]

#### 3.1.1 手动创建
1. **选择 Agent 类型**：展示支持的 Agent 类型卡片（Codex、OpenCode、Claude Code、Hermes）
2. **选择接入方式**：根据 Agent 类型展示可用接入方式（Desktop/Server/CLI）
3. **填写配置字段**：动态显示对应的配置字段表单，必填字段标红星
4. **实时验证**：字段失焦时执行格式验证，错误显示红色提示，警告显示黄色提示
5. **连接测试（可选）**：提供"测试连接"按钮，测试路径/URL 可访问性、数据库可读性
6. **保存与启用**：默认启用，或选择"保存但不启用"

#### 3.1.2 自动探测添加

**首次加载行为**：
- 首次打开配置页面时，**自动执行探测**，无需用户手动点击
- 探测完成后直接展示所有支持的 Agent 及其探测结果
- 用户无需额外操作即可看到哪些 Agent 已安装、哪些需要配置

**探测结果展示**：
- 按 Agent 类型分组显示（Codex、OpenCode、Claude Code、Hermes）
- **显示所有支持的 Agent**，即使未探测到也要展示占位卡片
- 每个探测结果显示：
  - Agent 名称和图标
  - 接入方式（Desktop/Server/CLI）
  - 探测状态：
    - **已探测到**（绿色勾）：发现完整数据文件，显示探测到的路径
    - **部分探测到**（黄色感叹号）：发现目录但缺少关键文件，显示探测到的路径
    - **未探测到**（灰色）：标准路径下未发现，提示"未在标准位置发现安装"
    - **需手动配置**（蓝色信息）：需要用户提供额外信息（如 OpenCode Server 地址）
  - 操作按钮：
    - **已探测到**：显示"添加"按钮（添加到 Profile 列表）
    - **部分探测到**：显示"编辑并添加"按钮（允许用户修改路径后添加）
    - **未探测到**：显示"手动配置"按钮（打开配置表单）
    - **需手动配置**：显示"配置"按钮（打开配置表单填写必要信息）

**探测结果示例布局**：

```
┌─────────────────────────────────────────────────┐
│ Agent 配置                      [重新探测]      │
├─────────────────────────────────────────────────┤
│                                                 │
│ Codex Desktop                                   │
│ ✓ 已探测到                                      │
│ 路径: ~/.codex                                  │
│ 发现: state_v1.sqlite (3 个会话)               │
│                              [添加到配置列表]   │
├─────────────────────────────────────────────────┤
│ OpenCode Desktop                                │
│ ⚠ 部分探测到                                    │
│ 路径: ~/.local/share/opencode                   │
│ 警告: 未找到 opencode.db 文件                   │
│                          [编辑并添加]           │
├─────────────────────────────────────────────────┤
│ OpenCode Server                                 │
│ ℹ 需手动配置                                    │
│ 说明: 需要提供服务器地址和认证信息              │
│                                   [配置]        │
├─────────────────────────────────────────────────┤
│ Claude Code Desktop                             │
│ ○ 未探测到                                      │
│ 说明: 未在标准位置发现安装                      │
│ 提示: 如已安装，点击手动配置                    │
│                              [手动配置]         │
├─────────────────────────────────────────────────┤
│ Hermes                                          │
│ ○ 未探测到                                      │
│ 说明: 未在标准位置发现安装                      │
│                              [手动配置]         │
└─────────────────────────────────────────────────┘
```

**交互流程**：
1. 用户首次进入配置页面，自动探测所有支持的 Agent
2. 探测完成后显示上述结果列表，展示所有支持的 Agent 类型
3. 用户点击"添加到配置列表"：
   - 已探测到的：直接使用探测到的配置创建 Profile
   - 部分探测到的：打开编辑表单，预填充探测到的路径，允许用户修改
   - 未探测到/需手动配置的：打开空白配置表单，用户填写完整信息
4. 添加后的 Profile 进入"已配置列表"，不再显示在探测结果中
5. 用户可以点击"重新探测"手动触发新一轮探测

**跳过与忽略**：
- 用户可以忽略某个探测结果（显示"以后不再提示"选项）
- 忽略后不在本次会话中再次显示
- 下次重新探测时会再次出现

### 3.2 编辑流程
**原型参考**: [agent-config-prototype.html](../../prototypes/agent-config-prototype.html) - [原型1.2.2]

- Profile 列表中点击"编辑"按钮进入编辑表单
- `profile_id`、`agent_type`、`adapter_kind` 不可修改（灰色只读）
- 其他字段均可修改
- 保存后自动清除之前的连接测试结果，触发新的连接验证

### 3.3 启用/停用
- **停用**：设置 `enabled=false`，停止发现会话，不删除配置数据和 Agent 原生文件
- **启用**：设置 `enabled=true`，下次刷新时开始发现会话，执行连接验证
- **停用确认**：如果该 Profile 下有活跃会话，显示警告并要求用户确认

### 3.4 删除
- **删除保护**：不允许删除有活跃会话的 Profile（executing/waiting_*）
- **删除流程**：
  1. 显示确认对话框，说明不会影响 Agent 原生安装和数据
  2. 如果有历史会话，提示会保留会话记录但无法再恢复执行
  3. 用户确认后从 Profile 列表和配置文件中删除

---

## 4. Agent 自动探测
**原型参考**: [agent-config-prototype.html](../../prototypes/agent-config-prototype.html) - [原型1.1]

### 4.1 探测范围
**原型参考**: [agent-config-prototype.html](../../prototypes/agent-config-prototype.html) - [原型1.1.1]

支持自动探测本地已安装的主流 Agent：
- **Codex**：Desktop 版本、CLI 版本
- **OpenCode**：Desktop 版本、Server 版本（需手动配置地址）
- **Claude Code**：Desktop 版本
- **Hermes**：Desktop 版本、CLI 版本

每种 Agent 的 Desktop 版本和 CLI 版本分开探测和配置。

### 4.2 探测可信度

- **高可信（已探测到）**：发现明确的数据库文件或可执行文件，路径准确，可以直接使用
- **中等（部分探测到）**：发现相关目录但缺少关键文件，可能需要验证或调整路径
- **需配置**：Agent 类型存在但需要手动配置端点或密码（如 OpenCode Server）
- **未探测到**：标准路径下未发现安装，需要手动配置

### 4.3 探测结果处理

- 探测结果可由用户选择性添加
- 添加后允许修改路径和参数以适应非标准安装
- 探测过程不修改任何 Agent 原生配置或文件系统
- 探测到的 Agent 配置添加后可正常通过探测验证并读取会话

### 4.4 平台特定探测路径

#### 4.4.1 Codex Desktop

**Windows**：
- 数据目录：`%USERPROFILE%\.codex`
- 探测文件：`state_*.sqlite`

**macOS**：
- 数据目录：`~/.codex`
- 探测文件：`state_*.sqlite`

**Linux**：
- 数据目录：`~/.codex`
- 探测文件：`state_*.sqlite`

#### 4.4.2 OpenCode Desktop

**Windows**：
- 数据目录：`%LOCALAPPDATA%\opencode` 或 `%APPDATA%\opencode`
- 探测文件：`opencode.db`

**macOS**：
- 数据目录：`~/Library/Application Support/opencode`
- 探测文件：`opencode.db`

**Linux**：
- 数据目录：`~/.local/share/opencode`
- 探测文件：`opencode.db`

#### 4.4.3 Claude Code Desktop

**Windows**：
- 数据目录：`%APPDATA%\Claude\Code` 或 `%LOCALAPPDATA%\Claude\Code`
- 探测文件：`state.db` 或 `sessions.db`

**macOS**：
- 数据目录：`~/Library/Application Support/Claude/Code`
- 探测文件：`state.db` 或 `sessions.db`

**Linux**：
- 数据目录：`~/.config/claude/code` 或 `~/.local/share/claude/code`
- 探测文件：`state.db` 或 `sessions.db`

#### 4.4.4 Hermes

**Windows**：
- 数据目录：`%USERPROFILE%\.hermes`
- 探测文件：`state.db`

**macOS**：
- 数据目录：`~/.hermes`
- 探测文件：`state.db`

**Linux**：
- 数据目录：`~/.hermes`
- 探测文件：`state.db`

---

## 5. 配置验证与诊断
**原型参考**: [agent-config-prototype.html](../../prototypes/agent-config-prototype.html) - [原型1.2.3]

### 5.1 验证时机
- **手动触发**：用户点击"测试连接"按钮
- **保存时验证**：可选，通过设置控制
- **定期验证**：后台定期检查已启用 Profile 的连接状态（每5分钟）

### 5.2 验证项目

#### 5.2.1 Codex Desktop
1. 检查 `codex_home` 目录是否存在
2. 检查是否有匹配 `db_file_pattern` 的文件
3. 尝试打开最新的数据库文件（只读模式）
4. 验证数据库 schema（检查 `threads` 表是否存在）
5. 测试深链是否注册（尝试解析 `codex://` URL）

#### 5.2.2 OpenCode Desktop
1. 检查 `db_path` 文件是否存在
2. 尝试打开数据库（只读模式）
3. 验证数据库 schema（检查 `session`、`message` 表是否存在）
4. 检查 `cli_executable` 是否可执行（如果配置了）

#### 5.2.3 OpenCode Server
1. 检查环境变量 `secret_env` 是否存在（不记录实际值）
2. 尝试连接 `server_url`（带超时）
3. 发送 GET `/api/session` 请求验证认证
4. 记录 API 版本信息（如果返回）

#### 5.2.4 Claude Code Desktop
1. 检查 `data_dir` 目录是否存在
2. 检查是否有匹配的数据库文件
3. 尝试打开数据库（只读模式）
4. 验证数据库 schema（检查会话相关表是否存在）

### 5.3 验证结果
- 在 Profile 中保存验证结果：
  - `last_verified_at`：最后验证时间
  - `verification_status`：成功/失败/警告
  - `verification_message`：详细信息或错误原因
- 验证结果在 Profile 列表中以图标和文字显示

### 5.4 诊断建议

根据验证失败原因，提供可操作的修复建议：

| 错误原因 | 修复建议 |
|---------|---------|
| 路径不存在 | "Agent 可能未安装或数据目录位置不正确，请检查安装路径" |
| 无读取权限 | "请检查文件系统权限，或以管理员身份运行 AgentHub" |
| 数据库打开失败 | "数据库文件可能损坏或被其他进程锁定，请关闭 Agent 后重试" |
| Server 连接失败 | "无法连接到服务器，请检查服务器是否运行以及网络连接" |
| 认证失败 | "认证失败，请检查环境变量 [变量名] 是否设置了正确的密码" |
| Schema 不匹配 | "数据库结构不匹配，可能是 Agent 版本不兼容" |
| CLI 不可执行 | "找不到 CLI 工具，精确恢复功能将不可用，可以指定完整路径" |

---

## 6. UI 与持久化

### 6.1 UI 交互规格

#### 6.1.1 Profile 列表展示
- **布局**：卡片式布局，每个 Profile 一张卡片
- **卡片内容**：
  - 左上：Agent 图标和类型
  - 标题：`profile_name`
  - 副标题：接入方式（Desktop/Server/CLI）
  - 状态指示器：启用/停用、连接状态（成功/失败/未验证）
  - 最后验证时间
  - 操作按钮：编辑、测试连接、启用/停用、删除

#### 6.1.2 筛选和排序
- **筛选**：按 Agent 类型、启用状态、连接状态
- **排序**：按创建时间（默认：最新在前）、按名称、按最后验证时间

#### 6.1.3 空状态
- 无 Profile 时显示所有支持的 Agent 探测结果
- 提供"重新探测"按钮和"手动添加"按钮

### 6.2 配置持久化

#### 6.2.1 存储位置
Profile 数据保存在 `~/.agenthub/agents.json`

#### 6.2.2 文件格式
```json
{
  "version": "1.0",
  "profiles": [
    {
      "profile_id": "uuid-string",
      "profile_name": "Codex Desktop",
      "agent_type": "codex",
      "adapter_kind": "codex_desktop",
      "enabled": true,
      "created_at": "2026-07-27T10:00:00Z",
      "updated_at": "2026-07-27T10:00:00Z",
      "installation_id": null,
      "config": {
        "codex_home": "~/.codex",
        "db_file_pattern": "state_*.sqlite",
        "deep_link_scheme": "codex://"
      },
      "verification": {
        "last_verified_at": "2026-07-27T10:05:00Z",
        "status": "success",
        "message": "连接成功，发现 5 个会话"
      }
    }
  ]
}
```

#### 6.2.3 文件管理
- 首次创建文件时设置权限为用户只读（600）
- 支持格式升级（通过 `version` 字段）
- 损坏时尝试从备份恢复（保留最近 3 个版本的备份）

### 6.3 安全性要求

#### 6.3.1 敏感信息处理
- **不在配置文件中存储密码**
- 密码通过环境变量传递，配置文件只保存变量名
- API 响应中不返回密码值
- 日志中不记录密码
- 命令行参数不包含密码（通过管道或文件传递）

#### 6.3.2 权限控制
- 配置文件设置为用户只读（Unix 权限 600）
- 数据库访问使用只读模式（where possible）
- 不执行任何写入 Agent 原生配置的操作

#### 6.3.3 安全验证
- URL 验证防止 SSRF 攻击
- 路径验证防止目录遍历
- 命令执行使用参数化方式，不拼接字符串

---

## 7. 验收标准

### 7.1 验收边界

#### 7.1.1 Profile 管理验收

| 验收项 | 验收标准 | 测试场景 |
|--------|----------|----------|
| 多 Profile 支持 | 能够为同一 Agent 产品创建多个 Profile（如两个 OpenCode Server） | 创建指向不同服务器的两个 OpenCode Server Profile，验证会话互不串扰 |
| Profile 隔离 | 单个 Profile 校验失败不影响其他 Profile | 停止一个 OpenCode Server，验证其他 Profile 仍能正常工作 |
| 稳定身份 | 其他模块通过稳定 Agent ID 使用配置 | Sessions 模块通过 Profile ID 获取 Adapter，不读取 UI 状态 |
| 字段验证 | 所有验证规则正确执行，错误提示准确 | 输入无效 URL、不存在的路径，验证提示内容和级别（错误/警告） |

#### 7.1.2 自动探测验收

| 验收项 | 验收标准 | 测试场景 |
|--------|----------|----------|
| 跨平台探测 | 在至少两个操作系统上成功发现已安装的 Agent | Windows + macOS 或 Windows + Linux 环境测试 |
| Desktop/CLI 区分 | 正确区分同一 Agent 的 Desktop 和 CLI 版本 | OpenCode Desktop 和 CLI 同时安装时，探测到两个不同的安装 |
| 探测状态准确 | 明确区分"未安装""无权限"和"尚未验证" | 无安装、有目录无文件、有文件无权限三种情况返回不同状态 |
| 首次自动探测 | 首次打开配置页面自动展示所有 Agent 探测状态 | 清空配置，重新打开页面，无需点击"探测"按钮即可看到结果 |
| 探测到可添加 | 探测到的 Agent 配置可添加并通过验证 | 探测到 Codex Desktop，点击"添加"，验证连接成功并能读取会话 |

#### 7.1.3 配置验证验收

| 验收项 | 验收标准 | 测试场景 |
|--------|----------|----------|
| Codex 验证 | 验证 codex_home、数据库文件、schema、深链 | 配置正确的 Codex Desktop，测试连接显示"成功，发现 N 个会话" |
| OpenCode Desktop 验证 | 验证 db_path、schema、CLI 工具 | 配置 OpenCode Desktop，CLI 不存在时显示警告但不阻止保存 |
| OpenCode Server 验证 | 验证环境变量、服务器连接、API 认证 | 配置错误密码，验证显示"认证失败"；配置正确后显示成功 |
| Claude Code 验证 | 验证 data_dir、数据库文件、schema | 配置 Claude Code Desktop，验证数据库结构检查通过 |
| 诊断建议准确 | 根据失败原因提供可操作建议 | 路径不存在时提示"请检查安装路径"，权限不足时提示"以管理员身份运行" |

#### 7.1.4 安全性验收

| 验收项 | 验收标准 | 测试场景 |
|--------|----------|----------|
| 密码不存储 | 配置文件、日志、API响应中不包含密码 | 配置 OpenCode Server，查看 agents.json 只有环境变量名 |
| 环境变量读取 | 运行时从环境读取密码 | 设置环境变量，验证 Adapter 能获取密码并连接成功 |
| 配置文件权限 | agents.json 设置为用户只读（600） | Unix 系统上创建配置文件，`ls -l` 验证权限为 -rw------- |
| 只读数据库 | 数据库访问使用只读模式 | 监控文件系统，验证不修改 Agent 原生数据库 |
| 路径安全 | 路径验证防止目录遍历 | 输入 `../../etc/passwd`，验证被拒绝 |

#### 7.1.5 UI 交互验收

| 验收项 | 验收标准 | 测试场景 |
|--------|----------|----------|
| 探测结果展示 | 显示所有支持的 Agent，包括未探测到的 | 未安装任何 Agent，仍显示 Codex/OpenCode/Claude Code/Hermes 卡片 |
| 状态图标 | 探测状态用不同颜色和图标表示 | 已探测到（绿色勾）、部分探测到（黄色感叹号）、未探测到（灰色） |
| 操作按钮 | 根据探测状态显示对应按钮 | 已探测到显示"添加"，未探测到显示"手动配置" |
| 编辑失败配置 | 部分探测到可编辑路径后添加 | OpenCode 只找到目录，点击"编辑并添加"修正路径后成功添加 |
| 重新探测 | 点击"重新探测"按钮刷新结果 | 探测后安装新 Agent，点击"重新探测"发现新安装 |
| 启用/停用 | 有活跃会话时显示确认对话框 | Profile 下有执行中会话，点击"停用"显示警告 |
| 删除保护 | 有活跃会话时不允许删除 | Profile 下有执行中会话，"删除"按钮禁用或点击后显示错误 |

### 7.2 测试用例

#### 7.2.1 基础配置流程

**测试用例 TC-A-001：手动创建 Codex Desktop Profile**
1. 打开配置页面
2. 点击"手动添加"
3. 选择 Agent 类型：Codex
4. 选择接入方式：Desktop
5. 填写 codex_home：`~/.codex`
6. 点击"测试连接"
7. 验证显示"连接成功"
8. 点击"保存"
9. 验证 Profile 列表中出现新 Profile

**预期结果**：Profile 创建成功，状态为"已启用"，验证状态为"成功"

**测试用例 TC-A-002：自动探测添加 OpenCode Desktop**
1. 确保本地已安装 OpenCode Desktop
2. 打开配置页面
3. 验证自动显示探测结果
4. 找到 OpenCode Desktop 卡片，状态为"已探测到"
5. 点击"添加到配置列表"
6. 验证 Profile 列表中出现新 Profile

**预期结果**：Profile 自动使用探测到的配置，无需手动填写

**测试用例 TC-A-003：配置 OpenCode Server 需手动输入**
1. 打开配置页面
2. 找到 OpenCode Server 卡片，状态为"需手动配置"
3. 点击"配置"
4. 填写 server_url：`http://localhost:8000`
5. 填写 secret_env：`OPENCODE_SERVER_PASSWORD`
6. 点击"测试连接"（假设环境变量未设置）
7. 验证显示"环境变量未设置"警告
8. 设置环境变量：`export OPENCODE_SERVER_PASSWORD=123456`
9. 再次点击"测试连接"
10. 验证显示"连接成功"

**预期结果**：Server 类型需要用户提供额外信息，环境变量正确提示

#### 7.2.2 边界情况测试

**测试用例 TC-A-004：路径不存在警告但允许保存**
1. 创建 Codex Desktop Profile
2. codex_home 填写不存在的路径：`/path/not/exist`
3. 验证显示黄色警告："路径不存在或无法访问"
4. 点击"保存"
5. 验证能够保存成功

**预期结果**：警告不阻止保存，允许配置未启动的 Agent

**测试用例 TC-A-005：同一类型多 Profile**
1. 创建第一个 OpenCode Server Profile，名称"本地服务器"，URL `http://localhost:8000`
2. 创建第二个 OpenCode Server Profile，名称"远程服务器"，URL `http://remote:8000`
3. 验证两个 Profile 独立存在
4. 分别测试连接
5. 启用/停用其中一个，验证另一个不受影响

**预期结果**：同类型 Agent 可创建多个 Profile，互不干扰

**测试用例 TC-A-006：Profile 名称唯一性**
1. 创建 Codex Desktop Profile，名称"开发环境"
2. 尝试创建另一个 Codex Desktop Profile，名称也是"开发环境"
3. 验证显示错误："配置名称不能重名"

**预期结果**：同一 agent_type + adapter_kind 下不允许重名

#### 7.2.3 跨平台测试

**测试用例 TC-A-007：Windows 平台探测**
- 验证 Codex：`%USERPROFILE%\.codex`
- 验证 OpenCode：`%LOCALAPPDATA%\opencode` 或 `%APPDATA%\opencode`
- 验证 Claude Code：`%APPDATA%\Claude\Code`

**测试用例 TC-A-008：macOS 平台探测**
- 验证 Codex：`~/.codex`
- 验证 OpenCode：`~/Library/Application Support/opencode`
- 验证 Claude Code：`~/Library/Application Support/Claude/Code`

**测试用例 TC-A-009：Linux 平台探测**
- 验证 Codex：`~/.codex`
- 验证 OpenCode：`~/.local/share/opencode`
- 验证 Claude Code：`~/.config/claude/code`

### 7.3 回归测试检查清单

在修改 Agents 模块代码后，应执行以下检查：

- [ ] 所有 Agent 类型的探测仍然工作
- [ ] 配置文件格式兼容（旧版本能升级）
- [ ] Profile 启用/停用不影响其他模块
- [ ] 敏感信息（密码）未泄露到日志或配置文件
- [ ] Sessions 模块能正常获取 Adapter
- [ ] UI 状态图标显示正确
- [ ] 错误提示文案准确友好
- [ ] 跨平台路径处理正确（Windows 反斜杠、Unix 正斜杠）

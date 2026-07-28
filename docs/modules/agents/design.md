# Agents 模块设计方案

本文档描述 Agents 模块的详细设计方案，包括需求拆解、流程说明、状态流转、数据结构、技术路线、接口设计、异常处理和实施计划。

## 1. 需求拆解

基于 [requirements.md](./requirements.md)，Agents 模块需求拆解为以下子系统：

### 1.1 Agent 自动探测子系统
- **探测引擎**：平台相关的路径扫描和文件检测
- **可信度评估**：根据发现的文件完整性判断探测可信度（已探测到/部分探测到/需配置/未探测到）
- **探测结果展示**：统一展示所有支持的 Agent 类型及其探测状态
- **跳过与忽略**：用户可忽略探测结果，下次刷新时重新出现

### 1.2 Profile 管理子系统
- **Profile CRUD**：创建、读取、更新、删除 Profile
- **字段验证**：路径、URL、环境变量名等字段格式和存在性验证
- **启用/停用**：控制 Profile 的激活状态，停用时保留数据但不再发现会话
- **删除保护**：禁止删除有活跃会话的 Profile

### 1.3 配置验证与诊断子系统
- **连接测试**：验证数据库、CLI、API 端点的可达性
- **路径验证**：检查文件和目录的存在性和权限
- **环境变量检查**：验证 secret_env 指定的环境变量是否存在
- **诊断建议**：根据验证失败原因提供具体修复建议

### 1.4 Adapter 工厂子系统
- **Adapter 注册**：维护 adapter_kind 到 Adapter 类的映射
- **Adapter 构造**：根据 Profile 配置实例化具体 Adapter
- **能力声明**：提供 Agent 对会话观察、任务执行、Skill、MCP、插件的支持状态

## 2. 核心流程说明

### 2.1 自动探测流程

```
用户进入配置页面
    ↓
触发自动探测
    ↓
并行扫描所有 Agent 类型
    ├─ Codex Desktop → 扫描 ~/.codex/state_*.sqlite
    ├─ OpenCode Desktop → 扫描 ~/.local/share/opencode/opencode.db
    ├─ OpenCode Server → 标记为"需配置"
    └─ Claude Code Desktop → 扫描平台相关数据目录
    ↓
汇总探测结果
    ↓
展示探测列表（所有支持的 Agent）
    ├─ ✓ 已探测到 → 显示路径，提供"添加到配置列表"按钮
    ├─ ⚠ 部分探测到 → 显示部分路径，提供"配置"按钮
    ├─ ℹ 需配置 → 显示说明，提供"配置"按钮
    └─ ○ 未探测到 → 显示提示，提供"手动配置"按钮
    ↓
用户选择操作
    ├─ 添加到配置列表 → 直接创建 Profile（已探测到）
    ├─ 配置 → 打开配置表单，预填充探测到的信息
    ├─ 手动配置 → 打开空白配置表单
    └─ 忽略 → 本次会话不再提示，下次刷新重新出现
```

### 2.2 Profile 创建流程

```
用户点击"添加配置"或探测结果的"配置"按钮
    ↓
显示配置表单
    ├─ 预填充探测到的信息（如果有）
    └─ 显示必填字段标记
    ↓
用户填写/修改配置
    ↓
前端字段验证
    ├─ 名称：2-50字符，同类型不重名
    ├─ 路径：绝对路径或 ~ 开头
    ├─ URL：有效的 HTTP/HTTPS URL
    └─ 环境变量名：符合命名规范
    ↓
提交保存
    ↓
后端验证
    ├─ 字段格式验证
    ├─ 路径存在性检查（警告）
    ├─ 连接测试（错误）
    └─ 环境变量检查（警告）
    ↓
验证结果
    ├─ 无错误 → 保存 Profile，状态标记为"正常"
    ├─ 仅警告 → 允许保存，显示警告提示
    └─ 有错误 → 拒绝保存，显示错误信息和修复建议
    ↓
保存成功
    ↓
自动触发连接验证
    ↓
更新 Profile 状态（成功/警告/错误）
```

### 2.3 Profile 启用/停用流程

```
启用流程：
用户点击"启用" → 设置 enabled=true → 触发连接验证 → 下次刷新开始发现会话

停用流程：
用户点击"停用"
    ↓
检查是否有活跃会话
    ├─ 有活跃会话 → 显示警告对话框，要求确认
    └─ 无活跃会话 → 直接停用
    ↓
用户确认
    ↓
设置 enabled=false
    ↓
停止发现该 Profile 的新会话
    ↓
已有会话仍可继续访问（不删除数据）
```

### 2.4 Profile 删除流程

```
用户点击"删除"
    ↓
检查删除保护条件
    ├─ 有活跃会话（executing/waiting_*） → 拒绝删除，显示错误提示
    └─ 无活跃会话 → 继续
    ↓
显示删除确认对话框
    ├─ 说明：不会影响 Agent 原生安装和数据
    └─ 如有历史会话：提示会保留会话记录但无法恢复执行
    ↓
用户确认
    ↓
从数据库删除 Profile
    ↓
从内存注册表移除
    ↓
历史会话保留但标记为"Profile 已删除"
```

## 3. 状态流转说明

### 3.1 Profile 状态流转

```
[未创建]
    ↓ 用户添加配置
[验证中] ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
    ↓ 验证完成              │
    ├─ 验证成功 → [正常]    │
    ├─ 有警告 → [警告]      │ 用户编辑配置
    └─ 有错误 → [错误] ─ ─ ─ ┘
                    ↓ 用户停用
                [已停用]
                    ↓ 用户删除
                [已删除]
```

**状态说明**：
- **验证中**：正在执行连接测试和路径检查
- **正常**：所有验证通过，可以正常使用
- **警告**：路径不存在或环境变量未设置，但允许使用（可能是 Agent 未启动）
- **错误**：连接失败或关键配置错误，无法使用
- **已停用**：用户主动停用，不再发现会话
- **已删除**：配置已删除，历史会话保留但无法恢复

### 3.2 探测状态流转

```
[未探测]
    ↓ 触发探测
[探测中]
    ↓ 探测完成
    ├─ 发现完整安装 → [已探测到] → 用户添加 → [已配置]
    ├─ 发现部分文件 → [部分探测到] → 用户配置 → [已配置]
    ├─ 需手动配置 → [需配置] → 用户配置 → [已配置]
    └─ 未发现安装 → [未探测到] → 用户忽略 → [已忽略]
                                         ↓ 下次刷新
                                    [未探测到]
```

## 4. 数据结构设计

### 4.1 AgentProfile 数据模型

```python
@dataclass
class AgentProfile:
    # 基本信息
    profile_id: str              # UUID，创建时生成
    profile_name: str            # 用户友好名称，2-50字符
    agent_type: AgentType        # codex/claude_code/opencode/hermes
    adapter_kind: AdapterKind    # 具体接入方式
    enabled: bool                # 是否启用
    
    # 时间戳
    created_at: datetime
    updated_at: datetime
    
    # 关联信息
    installation_id: str | None  # 关联的探测安装 ID
    
    # 类型特定配置（联合类型）
    config: AgentConfig          # 根据 adapter_kind 的具体配置
    
    # 验证状态
    validation_status: ValidationStatus  # normal/warning/error
    last_validated_at: datetime | None
    validation_messages: list[ValidationMessage]
```

### 4.2 AgentConfig 联合类型

```python
@dataclass
class CodexDesktopConfig:
    codex_home: Path
    db_file_pattern: str = "state_*.sqlite"
    deep_link_scheme: str = "codex://"

@dataclass
class OpenCodeDesktopConfig:
    db_path: Path
    cli_executable: str = "opencode"

@dataclass
class OpenCodeServerConfig:
    server_url: str              # http://localhost:8000
    secret_env: str              # 环境变量名
    cli_executable: str = "opencode"
    timeout_seconds: int = 30
    verify_ssl: bool = True

@dataclass
class ClaudeCodeDesktopConfig:
    data_dir: Path
    db_file_name: str = "state.db"

AgentConfig = CodexDesktopConfig | OpenCodeDesktopConfig | OpenCodeServerConfig | ClaudeCodeDesktopConfig
```

### 4.3 探测结果数据模型

```python
@dataclass
class DetectionResult:
    agent_type: AgentType
    adapter_kind: AdapterKind
    status: DetectionStatus      # detected/partial/needs_config/not_found
    confidence: float            # 0.0-1.0
    discovered_paths: dict[str, Path]  # 发现的路径
    missing_components: list[str]      # 缺失的组件
    message: str                       # 用户可读的说明
    suggestions: list[str]             # 修复建议
```

### 4.4 验证结果数据模型

```python
@dataclass
class ValidationMessage:
    level: ValidationLevel       # error/warning/info
    field: str                   # 相关字段名
    message: str                 # 错误信息
    suggestion: str | None       # 修复建议

@dataclass
class ValidationResult:
    success: bool
    status: ValidationStatus     # normal/warning/error
    messages: list[ValidationMessage]
    tested_at: datetime
```

## 5. 技术路线

### 5.1 探测引擎实现

**平台检测**：
- 使用 `platform.system()` 识别 Windows/macOS/Linux
- 根据平台选择不同的探测路径

**路径扫描**：
- 使用 `pathlib.Path` 进行路径操作
- 使用 `glob` 模式匹配数据库文件
- 检查文件存在性和读取权限

**并行探测**：
- 使用 `asyncio.gather()` 并行探测多个 Agent
- 每个 Agent 的探测超时 5 秒

### 5.2 配置验证实现

**分层验证**：
1. **格式验证**（前端 + 后端）：字段类型、长度、格式
2. **存在性验证**（后端，警告级别）：路径、文件是否存在
3. **连接验证**（后端，错误级别）：数据库连接、API 可达性

**验证策略**：
- 路径不存在 → 警告，允许保存（Agent 可能未启动）
- 连接失败 → 错误，允许保存但标记错误状态
- 格式错误 → 错误，拒绝保存

### 5.3 持久化实现

**存储方案**：
- 使用 SQLite 存储 Profile 配置
- 表结构：`agent_profiles` 表
- 密码等敏感信息不存储，仅存储环境变量名

**配置文件位置**：
- `~/.agenthub/config.db`
- 首次启动自动创建

### 5.4 Adapter 工厂实现

**注册机制**：
```python
class AdapterFactory:
    _registry: dict[AdapterKind, type[AgentAdapter]] = {}
    
    @classmethod
    def register(cls, kind: AdapterKind, adapter_class: type[AgentAdapter]):
        cls._registry[kind] = adapter_class
    
    @classmethod
    def create(cls, profile: AgentProfile) -> AgentAdapter:
        adapter_class = cls._registry.get(profile.adapter_kind)
        if not adapter_class:
            raise ValueError(f"Unknown adapter kind: {profile.adapter_kind}")
        return adapter_class(profile)
```

**能力声明**：
每个 Adapter 实现 `get_capabilities()` 方法返回能力矩阵

## 6. 接口设计

### 6.1 探测接口

```python
async def detect_agents() -> list[DetectionResult]:
    """自动探测所有支持的 Agent"""
    
async def detect_agent(agent_type: AgentType) -> DetectionResult:
    """探测特定 Agent"""
```

### 6.2 Profile 管理接口

```python
async def create_profile(config_input: ProfileCreateInput) -> AgentProfile:
    """创建新 Profile"""
    
async def update_profile(profile_id: str, updates: ProfileUpdateInput) -> AgentProfile:
    """更新 Profile"""
    
async def delete_profile(profile_id: str) -> None:
    """删除 Profile（有保护检查）"""
    
async def enable_profile(profile_id: str) -> None:
    """启用 Profile"""
    
async def disable_profile(profile_id: str) -> None:
    """停用 Profile"""
    
async def list_profiles(enabled_only: bool = False) -> list[AgentProfile]:
    """列出所有 Profile"""
    
async def get_profile(profile_id: str) -> AgentProfile:
    """获取单个 Profile"""
```

### 6.3 验证接口

```python
async def validate_profile(profile: AgentProfile) -> ValidationResult:
    """验证 Profile 配置"""
    
async def test_connection(profile: AgentProfile) -> bool:
    """测试连接"""
```

### 6.4 Adapter 工厂接口

```python
def create_adapter(profile: AgentProfile) -> AgentAdapter:
    """根据 Profile 创建 Adapter"""
    
def get_capabilities(profile: AgentProfile) -> CapabilityMatrix:
    """获取能力声明"""
```

## 7. 异常处理

### 7.1 探测异常

| 异常情况 | 处理策略 |
|---------|---------|
| 路径不可访问 | 标记为"未探测到"，记录日志 |
| 权限不足 | 标记为"部分探测到"，提示需要权限 |
| 文件损坏 | 标记为"部分探测到"，建议重新安装 |
| 探测超时 | 标记为"未探测到"，允许手动配置 |

### 7.2 配置验证异常

| 异常情况 | 严重级别 | 处理策略 |
|---------|---------|---------|
| 路径不存在 | 警告 | 允许保存，显示警告 |
| 无读取权限 | 错误 | 允许保存但标记错误状态 |
| 数据库连接失败 | 错误 | 允许保存但标记错误状态 |
| API 端点不可达 | 错误 | 允许保存但标记错误状态 |
| 环境变量不存在 | 警告 | 允许保存，提示设置环境变量 |
| 字段格式错误 | 错误 | 拒绝保存，显示格式要求 |

### 7.3 运行时异常

| 异常情况 | 处理策略 |
|---------|---------|
| Profile 已删除 | 返回 404，前端显示友好提示 |
| 有活跃会话时删除 | 返回 409，显示活跃会话列表 |
| Adapter 创建失败 | 记录日志，返回错误信息给前端 |
| 并发修改冲突 | 使用乐观锁，提示用户刷新重试 |

## 8. 实施计划

### 8.1 第一阶段：探测引擎（1-2天）
- [ ] 实现平台检测逻辑
- [ ] 实现 Codex Desktop 探测
- [ ] 实现 OpenCode Desktop 探测
- [ ] 实现 Claude Code Desktop 探测
- [ ] 实现探测结果汇总
- [ ] 编写探测单元测试

### 8.2 第二阶段：Profile 管理（2-3天）
- [ ] 设计数据库表结构
- [ ] 实现 Profile CRUD 接口
- [ ] 实现字段验证逻辑
- [ ] 实现启用/停用流程
- [ ] 实现删除保护检查
- [ ] 编写 Profile 管理单元测试

### 8.3 第三阶段：配置验证（1-2天）
- [ ] 实现路径验证
- [ ] 实现连接测试（数据库/API）
- [ ] 实现环境变量检查
- [ ] 实现验证结果持久化
- [ ] 编写验证逻辑单元测试

### 8.4 第四阶段：UI 实现（2-3天）
- [ ] 实现探测结果展示页面
- [ ] 实现 Profile 列表页面
- [ ] 实现配置表单组件
- [ ] 实现验证状态可视化
- [ ] 实现删除确认对话框
- [ ] 编写 UI 集成测试

### 8.5 第五阶段：集成与测试（1-2天）
- [ ] 端到端流程测试
- [ ] 多平台兼容性测试
- [ ] 异常场景测试
- [ ] 性能测试（探测速度）
- [ ] 用户体验优化

**总计：7-12 个工作日**

## 9. 风险与对策

### 9.1 技术风险

| 风险 | 影响 | 概率 | 对策 |
|-----|------|------|------|
| 平台差异导致探测失败 | 高 | 中 | 提供手动配置入口，详细文档 |
| Agent 更新导致路径变化 | 中 | 中 | 版本化探测逻辑，社区反馈机制 |
| 并发修改导致数据不一致 | 中 | 低 | 使用乐观锁，检测冲突 |
| 敏感信息泄露 | 高 | 低 | 严格审查，只存储环境变量名 |

### 9.2 产品风险

| 风险 | 影响 | 概率 | 对策 |
|-----|------|------|------|
| 探测误报影响用户信任 | 高 | 中 | 明确标识可信度，允许忽略 |
| 配置过于复杂 | 中 | 中 | 自动探测优先，简化表单 |
| 删除保护过于严格 | 低 | 低 | 提供强制删除选项（专家模式） |

---

## 附录：职责与依赖

### 职责

Agents 是接入层的领域入口，维护 Agent 身份、安装、Profile 和 Adapter 注册表。它不负责解释会话状态、编排任务，也不直接执行能力共享或删除。

### 核心模型

- `AgentType`：Codex、Claude Code、OpenCode 等产品类型。
- `AgentInstallation`：本机发现的一份安装，包含版本、可执行文件和平台信息。
- `AgentProfile`：用户启用的接入配置，引用安装并保存 Adapter 参数。
- `AgentCapabilityMatrix`：会话观察、任务执行、Skill、MCP、插件的支持状态、限制和验证等级。
- `AdapterRegistration`：Agent 类型到 Adapter 工厂及其版本约束的注册关系。

### 对外接口

- 查询已启用 Profile 和稳定 Agent ID。
- 校验 Profile 的连接、目录、配置和恢复入口。
- 获取某 Agent 对会话观察、任务执行或某类能力的支持声明。
- 为 `sessions`、`workflows` 和 `capabilities` 创建对应 Adapter。

### 依赖边界

- `sessions` 通过 Agent Adapter 会话契约读取会话和执行精确恢复。
- `workflows` 通过 Agent 执行 Adapter 新建会话、继续指定会话并发送用户确认的任务。
- `capabilities` 通过 Agent Adapter 能力契约获取发现位置、原生注册方式和加载状态。
- `operations` 使用已校验的 Profile 和 Adapter 执行原生变更。
- UI 不直接解释 Agent 原生配置，也不直接调用系统命令。

### 持久化

数据库保存 Profile、用户选择、能力声明缓存和验证记录；Agent 安装、原生 API、配置文件和文件系统仍是事实来源。每次连接验证应刷新缓存并保留失败原因。

### 当前实现

- `src/agent_hub/agents/models.py`：Agent Profile、配置输入与会话接入能力声明。
- `src/agent_hub/agents/config.py`：Profile JSON 持久化与首次候选配置。
- `src/agent_hub/agents/registry.py`：运行时 Profile 查询与连接状态更新 Interface。
- `src/agent_hub/adapter_factory.py`：Adapter 类型目录、Profile 标准化与真实 Adapter 构造。
- `src/agent_hub/bootstrap.py`：在应用组合入口创建可重载 Registry 和 SessionHub。

当前 Adapter 只覆盖会话发现和恢复，因此作为 Session Adapter 放在 `sessions` 模块，避免 `agents` 反向依赖会话模型。未来出现跨会话、能力等多个真实 Adapter 实现后，再从已验证的共同点提取更高层 Agent Adapter。

### OpenCode 注册

OpenCode Server 保留 `create_opencode_runtime` 作为验证和兼容入口；生产默认运行时通过 `AgentAdapterFactory` 从 Profile 注册。Profile 只保存 Server 地址、密码环境变量名、能力声明和状态来源；Basic Auth 密码由运行时注入 Adapter，不进入 Profile、日志或恢复目标。

- 会话发现：完整支持，来源为 OpenCode Server `/api/session`。
- 独立状态：轮询支持；运行中状态可直接映射，历史 inactive/idle 不推断为完成。
- Todo 读取：完整支持，来源为 `/session/{sessionID}/todo`。
- 精确恢复：官方 CLI 命令和进程存活已验证，仍待人工确认 TUI 展示了指定会话内容。
- 事件流：首版未接入，声明为不支持，使用轮询保证最终刷新。

### Codex 注册

Codex 保留 `create_codex_runtime` 作为验证和兼容入口；生产默认运行时自动发现本机 Codex Desktop Profile。Profile 只声明本地状态轮询和 Desktop 深链能力，不保存账号、Token 或 API Key。

- 会话发现：完整支持，来源为 `CODEX_HOME` 中版本号最大的 `state_*.sqlite`。
- 独立状态：支持 rollout 生命周期轮询，可识别执行中、等待输入、已结束和中断。
- 规划读取：支持当前轮次最近一次 `update_plan`。
- 精确恢复：使用 `codex://threads/<thread-id>` 在 Codex Desktop 中定位原生任务。
- 事件流：首版未接入，声明为不支持；等待授权等只存在于 App Server 内存通知的状态暂不推断。

### 统一 Profile 配置实现

生产入口使用 `create_configured_runtime`，不再默认启动 Demo Runtime。`AgentProfileStore` 将配置保存到 `~/.agenthub/agents.json`，支持新增、编辑、启停和删除；首次没有配置文件时自动生成 Codex Desktop 与 OpenCode Desktop 候选 Profile。

产品类型与接入 Profile 分开建模。同一 OpenCode 产品可以同时存在 `opencode_desktop` 与 `opencode_server`，两者使用独立 Profile ID、连接状态和会话身份，不按显示名称合并。`AgentAdapterFactory` 根据 `adapter_kind` 构造 Adapter，单个 Profile 配置错误不会阻断其他 Profile。

OpenCode Server Profile 只保存 `secret_env`，例如 `OPENCODE_SERVER_PASSWORD`；密码值只在构造 Adapter 时从进程环境读取，不写入 JSON、API 响应、日志或恢复命令。页面提供以下接入类型：

- `codex_desktop`：Codex 本地状态与 Desktop 深链。
- `opencode_desktop`：OpenCode Desktop 本地 SQLite 与官方 CLI Resume。
- `opencode_server`：OpenCode Server API 与 CLI Attach。

OpenCode Server 的 `resume_launch` 为已验证，`exact_resume` 在人工确认目标 TUI 内容前保持 `false`；两者不得因为使用了同一个 CLI 参数而合并声明。

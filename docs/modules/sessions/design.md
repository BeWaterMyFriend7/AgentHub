# Sessions 模块设计方案

本文档描述 Sessions 模块的详细设计方案，包括需求拆解、流程说明、状态流转、数据结构、技术路线、接口设计、异常处理和实施计划。

## 1. 需求拆解

基于 [requirements.md](./requirements.md)，Sessions 模块需求拆解为以下子系统：

### 1.1 会话发现与展示子系统
- **会话聚合引擎**：从多个 Agent Adapter 收集会话
- **状态归一化**：将不同 Agent 的状态映射到统一模型
- **信息展示**：展示会话基本信息、当前目标、最近活动
- **统计汇总**：按运行状态、关注状态汇总统计

### 1.2 状态管理子系统
- **运行状态映射**：将 Agent 原生状态映射到统一运行状态
- **系统关注状态推导**：基于可信事件自动推导是否需要介入
- **状态来源追踪**：记录状态来源和可信度
- **状态更新通知**：状态变化时通知相关模块

### 1.3 用户跟进标记子系统
- **待跟进标记**：用户主动标记需要稍后处理的会话
- **已忽略标记**：用户标记中断会话为正常退出
- **标记持久化**：绑定到 Profile + 原生会话 ID
- **提醒功能**：到达提醒时间时桌面通知

### 1.4 筛选与搜索子系统
- **多维度筛选**：运行状态、关注状态、用户标记、Agent 类型、Profile、项目、时间
- **组合筛选**：支持多个筛选条件同时生效
- **全文搜索**：搜索标题、目标、项目路径
- **筛选状态持久化**：记住用户的筛选偏好

### 1.5 刷新与同步子系统
- **自动刷新**：定时轮询 Adapter 获取最新会话状态
- **手动刷新**：用户主动触发全量刷新
- **增量更新**：支持 Agent 的事件流接入
- **冲突处理**：处理本地标记与远程状态的冲突

### 1.6 精确恢复子系统
- **恢复入口选择**：按官方 API、CLI、深链、窗口激活顺序降级
- **命令生成**：生成精确恢复命令（含原生会话 ID）
- **恢复验证**：验证恢复命令是否成功打开目标会话
- **降级策略**：主恢复方式失败时尝试备选方式

## 2. 核心流程说明

### 2.1 会话发现与更新流程

```
触发刷新（定时/手动/事件驱动）
    ↓
获取所有已启用的 Agent Profile
    ↓
并行调用各 Profile 的 Adapter
    ├─ CodexDesktopAdapter.list_sessions()
    ├─ OpenCodeDesktopAdapter.list_sessions()
    ├─ OpenCodeServerAdapter.list_sessions()
    └─ ClaudeCodeDesktopAdapter.list_sessions()
    ↓
汇总所有会话
    ↓
对每个会话：
    ├─ 生成稳定内部 ID（Profile ID + 原生会话 ID）
    ├─ 映射运行状态
    ├─ 推导系统关注状态
    ├─ 合并本地 SessionAnnotation
    └─ 更新读模型
    ↓
生成统计数据
    ├─ 会话总数
    ├─ 按运行状态统计
    ├─ 按关注状态统计
    └─ 按用户标记统计
    ↓
返回会话列表和统计
```

### 2.2 系统关注状态推导流程

```
获取会话的运行状态
    ↓
根据规则推导系统关注状态：
    ├─ waiting_permission → 需要介入（等待授权）
    ├─ waiting_input → 需要介入（等待输入）
    ├─ interrupted → 需要介入（执行中断）
    ├─ waiting_review → 需要介入（等待验收）
    ├─ executing → 无需介入（正常执行）
    ├─ closed → 无需介入（已关闭）
    └─ unknown → 无需介入（状态未知）
    ↓
检查后续事件是否解除关注状态：
    ├─ 等待授权/输入 → 观察到恢复执行事件 → 解除
    ├─ 执行中断 → 观察到恢复执行事件 → 解除
    └─ 等待验收 → 用户发送指令/会话关闭 → 解除
    ↓
标记状态来源和可信度
    ├─ 来自 Agent 明确事件 → 高可信度
    ├─ 推断自轮询状态 → 中等可信度
    └─ 缺失关键证据 → 低可信度
```

### 2.3 用户标记流程

```
待跟进标记流程：
用户点击”标记跟进”
    ↓
显示标记对话框
    ├─ 选择标签（预定义 + 自定义）
    ├─ 输入备注（最多500字符）
    └─ 设置提醒时间（可选）
    ↓
用户点击”保存”
    ↓
验证输入
    ├─ 标签数量 ≤ 5
    ├─ 备注长度 ≤ 500
    └─ 提醒时间 ≥ 当前时间
    ↓
写入 session_annotations 表
    ├─ follow_up_mark = true
    ├─ follow_up_tags = JSON数组
    ├─ follow_up_note = 备注文本
    └─ follow_up_remind_at = 提醒时间
    ↓
更新会话显示（添加”待跟进”徽章）
    ↓
如果设置了提醒时间：
    └─ 注册定时任务，到时发送桌面通知

已忽略标记流程：
用户点击”忽略”（仅限中断会话）
    ↓
显示忽略对话框
    ├─ 选择忽略原因（预定义选项）
    └─ 输入补充说明（可选，最多200字符）
    ↓
用户点击”确认忽略”
    ↓
验证输入
    └─ 说明长度 ≤ 200
    ↓
写入 session_annotations 表
    ├─ ignored_mark = true
    ├─ ignored_reason = 原因
    └─ ignored_note = 补充说明
    ↓
会话从待处理列表中隐藏（默认不显示）
```

### 2.4 筛选与搜索流程

```
用户修改筛选条件
    ↓
更新筛选状态
    ├─ 运行状态筛选
    ├─ 关注状态筛选
    ├─ 用户标记筛选
    ├─ Agent 类型筛选
    ├─ Profile 筛选
    ├─ 项目筛选
    └─ 时间范围筛选
    ↓
应用筛选逻辑（多条件 AND）
    ↓
显示筛选标签（可移除）
    ↓
过滤会话列表
    ↓
更新统计数字（仅统计可见会话）

搜索流程：
用户输入搜索关键词
    ↓
实时搜索（防抖 300ms）
    ↓
在以下字段中搜索：
    ├─ 会话标题
    ├─ 当前目标
    ├─ 项目路径
    └─ 最近活动
    ↓
显示匹配的会话
    ↓
高亮关键词
```

### 2.5 精确恢复流程

```
用户点击”打开”按钮
    ↓
获取会话的恢复能力声明
    ↓
按优先级选择恢复方式：
    1. 官方 API（如支持）
    2. CLI Resume 命令
    3. 深度链接
    4. 窗口激活（降级）
    ↓
生成恢复命令/URL
    ├─ 包含原生会话 ID
    ├─ 包含工作目录（如需要）
    └─ 认证信息从环境变量注入
    ↓
执行恢复操作
    ├─ API 调用：发送 HTTP 请求
    ├─ CLI 命令：启动子进程
    ├─ 深度链接：打开 URL
    └─ 窗口激活：查找并激活窗口
    ↓
验证恢复结果
    ├─ 成功 → 记录恢复成功
    ├─ 失败 → 尝试降级方式
    └─ 所有方式失败 → 显示错误提示
```

## 3. 状态流转说明

### 3.1 运行状态流转

```
[executing] 执行中
    ↓ Agent 请求授权
[waiting_permission] 等待授权
    ↓ 用户授权 / Agent 继续执行
[executing] 执行中
    ↓ Agent 请求输入
[waiting_input] 等待输入
    ↓ 用户输入 / Agent 继续执行
[executing] 执行中
    ↓ 任务完成
[waiting_review] 等待验收
    ↓ 用户验收 / 发送新指令
[executing] 执行中 / [closed] 已关闭
    
[executing] 执行中
    ↓ 发生错误 / 异常中断
[interrupted] 执行中断
    ↓ 用户修复后继续
[executing] 执行中

[executing] 执行中
    ↓ 用户关闭会话
[closed] 已关闭

任何状态
    ↓ 无法确定状态
[unknown] 状态未知
```

### 3.2 系统关注状态流转

```
[无需介入]
    ↓ 运行状态变为 waiting_permission/waiting_input/interrupted/waiting_review
[需要介入]
    ↓ 观察到恢复执行事件 / 用户处理完成
[无需介入]
```

### 3.3 用户标记状态流转

```
[未标记]
    ↓ 用户添加待跟进标记
[待跟进]
    ↓ 用户取消标记 / 会话关闭
[未标记]

[未标记]
    ↓ 用户标记为已忽略
[已忽略]
    ↓ 用户取消标记
[未标记]
```

## 4. 数据结构设计

### 4.1 AgentSession 数据模型

```python
@dataclass
class AgentSession:
    # 身份信息
    internal_id: str              # 稳定内部 ID（Profile ID + 原生会话 ID）
    agent_profile_id: str         # Agent Profile ID
    native_session_id: str        # 原生会话 ID
    
    # 基本信息
    title: str                    # 会话标题
    project_path: str | None      # 项目或工作目录
    
    # 状态信息
    running_status: RunningStatus          # 运行状态
    attention_status: AttentionStatus      # 系统关注状态
    status_source: str                     # 状态来源描述
    status_confidence: Confidence          # 状态可信度（high/medium/low）
    
    # 目标与活动
    current_goal: str | None      # 当前目标
    plan_items: list[PlanItem]    # 计划项列表
    recent_activity: str | None   # 最近活动描述
    
    # 时间戳
    created_at: datetime          # 创建时间
    updated_at: datetime          # 最后更新时间
    last_activity_at: datetime    # 最后活动时间
    
    # 恢复能力
    resume_method: ResumeMethod   # 恢复方式（api/cli/deeplink/window）
    resume_command: str | None    # 恢复命令或 URL
    access_level: AccessLevel     # 接入等级（full/limited/readonly）
    
    # 用户标记（可选，从 SessionAnnotation 合并）
    annotation: SessionAnnotation | None
```

### 4.2 SessionAnnotation 数据模型

```python
@dataclass
class SessionAnnotation:
    # 关联信息
    agent_profile_id: str
    native_session_id: str
    
    # 待跟进标记
    follow_up_mark: bool = False
    follow_up_tags: list[str] = field(default_factory=list)
    follow_up_note: str = “”
    follow_up_remind_at: datetime | None = None
    
    # 已忽略标记
    ignored_mark: bool = False
    ignored_reason: str = “”
    ignored_note: str = “”
    
    # 时间戳
    marked_at: datetime
    updated_at: datetime
```

### 4.3 运行状态枚举

```python
class RunningStatus(str, Enum):
    EXECUTING = “executing”              # 执行中
    WAITING_PERMISSION = “waiting_permission”  # 等待授权
    WAITING_INPUT = “waiting_input”      # 等待输入
    WAITING_REVIEW = “waiting_review”    # 等待验收
    INTERRUPTED = “interrupted”          # 执行中断
    CLOSED = “closed”                    # 已关闭
    UNKNOWN = “unknown”                  # 状态未知
```

### 4.4 系统关注状态枚举

```python
class AttentionStatus(str, Enum):
    NEEDS_ATTENTION = “needs_attention”  # 需要介入
    NO_ATTENTION = “no_attention”        # 无需介入
```

### 4.5 筛选条件数据模型

```python
@dataclass
class SessionFilter:
    running_status: list[RunningStatus] | None = None
    attention_status: AttentionStatus | None = None
    user_mark: UserMarkFilter | None = None  # all/follow_up/ignored/unmarked
    agent_types: list[AgentType] | None = None
    profile_ids: list[str] | None = None
    project_paths: list[str] | None = None
    time_range: TimeRange | None = None      # last_hour/today/last_7_days/earlier
    search_keyword: str | None = None
    hide_ignored: bool = True                # 默认隐藏已忽略
```

### 4.6 统计数据模型

```python
@dataclass
class SessionStatistics:
    total_count: int
    executing_count: int
    needs_attention_count: int
    waiting_review_count: int
    interrupted_count: int
    follow_up_count: int
    by_agent_type: dict[AgentType, int]
    by_profile: dict[str, int]
```

## 5. 技术路线

### 5.1 会话聚合实现

**并行拉取**：
- 使用 `asyncio.gather()` 并行调用所有 Adapter
- 单个 Adapter 超时 30 秒
- Adapter 失败不影响其他 Adapter

**身份归一化**：
- 使用 `f”{profile_id}:{native_session_id}”` 作为稳定内部 ID
- 保证同一原生会话在不同刷新中 ID 一致

**状态映射**：
- 每个 Adapter 实现 `map_running_status()` 方法
- 统一的状态推导规则

### 5.2 标记持久化实现

**数据库表结构**：
```sql
CREATE TABLE session_annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_profile_id TEXT NOT NULL,
    native_session_id TEXT NOT NULL,
    follow_up_mark BOOLEAN DEFAULT FALSE,
    follow_up_tags TEXT,  -- JSON array
    follow_up_note TEXT,
    follow_up_remind_at DATETIME,
    ignored_mark BOOLEAN DEFAULT FALSE,
    ignored_reason TEXT,
    ignored_note TEXT,
    marked_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE(agent_profile_id, native_session_id)
);

CREATE INDEX idx_follow_up ON session_annotations(follow_up_mark, follow_up_remind_at);
CREATE INDEX idx_ignored ON session_annotations(ignored_mark);
```

**合并策略**：
- 刷新会话时自动 JOIN 标记表
- 标记优先级高于系统推导

### 5.3 筛选与搜索实现

**筛选实现**：
- 前端构造 `SessionFilter` 对象
- 后端应用多条件 AND 逻辑
- 使用 SQL WHERE 子句优化性能

**搜索实现**：
- 使用 SQLite FTS（全文搜索）索引
- 搜索字段：title, current_goal, project_path, recent_activity
- 前端防抖 300ms 减少请求

### 5.4 刷新策略实现

**三种刷新方式**：
1. **自动刷新**：定时轮询，默认 30 秒
2. **手动刷新**：用户点击刷新按钮
3. **事件驱动**：Agent 支持事件流时实时更新

**刷新优化**：
- 仅刷新可见会话的详细信息
- 统计数据增量计算
- 使用 ETag / Last-Modified 避免重复拉取

### 5.5 精确恢复实现

**命令生成**：
```python
def generate_resume_command(session: AgentSession) -> str:
    if session.adapter_kind == AdapterKind.OPENCODE_SERVER:
        return f”opencode attach {server_url} --session {native_id} --dir {directory}”
    elif session.adapter_kind == AdapterKind.CODEX_DESKTOP:
        return f”codex://threads/{native_id}”
    elif session.adapter_kind == AdapterKind.OPENCODE_DESKTOP:
        return f”opencode {directory} --session {native_id}”
    else:
        raise NotImplementedError()
```

**安全处理**：
- 密码从环境变量注入，不出现在命令行
- 命令日志脱敏
- 恢复失败时不暴露敏感信息

## 6. 接口设计

### 6.1 会话查询接口

```python
async def list_sessions(filter: SessionFilter | None = None) -> list[AgentSession]:
    “””列出所有会话（支持筛选）”””
    
async def get_session(internal_id: str) -> AgentSession:
    “””获取单个会话详情”””
    
async def get_statistics() -> SessionStatistics:
    “””获取统计数据”””
    
async def refresh_sessions() -> None:
    “””手动触发刷新”””
```

### 6.2 标记管理接口

```python
async def mark_follow_up(
    internal_id: str,
    tags: list[str],
    note: str = “”,
    remind_at: datetime | None = None
) -> None:
    “””标记为待跟进”””
    
async def unmark_follow_up(internal_id: str) -> None:
    “””取消待跟进标记”””
    
async def mark_ignored(
    internal_id: str,
    reason: str,
    note: str = “”
) -> None:
    “””标记为已忽略”””
    
async def unmark_ignored(internal_id: str) -> None:
    “””取消已忽略标记”””
```

### 6.3 恢复接口

```python
async def resume_session(internal_id: str) -> ResumeResult:
    “””恢复会话到 Agent 原生界面”””
    
async def get_resume_command(internal_id: str) -> str:
    “””获取恢复命令（用于复制）”””
```

## 7. 异常处理

### 7.1 Adapter 异常

| 异常情况 | 处理策略 |
|---------|---------|
| Adapter 连接失败 | 跳过该 Profile，记录日志，不影响其他 Profile |
| Adapter 超时 | 30秒超时，标记 Profile 为断开状态 |
| 数据格式错误 | 记录错误，跳过该会话，继续处理其他会话 |
| 权限不足 | 显示友好错误，提示检查配置 |

### 7.2 标记操作异常

| 异常情况 | 处理策略 |
|---------|---------|
| 会话不存在 | 返回 404，提示会话可能已关闭 |
| 标签数量超限 | 返回 400，提示最多 5 个标签 |
| 备注过长 | 返回 400，提示长度限制 |
| 提醒时间无效 | 返回 400，提示时间必须在未来 |
| 数据库写入失败 | 返回 500，记录详细日志 |

### 7.3 恢复操作异常

| 异常情况 | 处理策略 |
|---------|---------|
| 恢复命令失败 | 尝试降级方式，显示错误提示 |
| Agent 未启动 | 提示启动 Agent 后重试 |
| 会话已被删除 | 提示会话在 Agent 中已不存在 |
| 环境变量缺失 | 提示设置必需的环境变量 |

## 8. 实施计划

### 8.1 第一阶段：会话聚合（2-3天）
- [ ] 实现并行 Adapter 调用
- [ ] 实现身份归一化
- [ ] 实现状态映射逻辑
- [ ] 实现统计数据计算
- [ ] 编写聚合单元测试

### 8.2 第二阶段：标记系统（2-3天）
- [ ] 设计数据库表结构
- [ ] 实现标记 CRUD 接口
- [ ] 实现标记与会话合并
- [ ] 实现提醒定时任务
- [ ] 编写标记单元测试

### 8.3 第三阶段：筛选搜索（1-2天）
- [ ] 实现多维度筛选逻辑
- [ ] 实现全文搜索
- [ ] 实现筛选状态持久化
- [ ] 优化筛选性能
- [ ] 编写筛选单元测试

### 8.4 第四阶段：刷新策略（1-2天）
- [ ] 实现定时自动刷新
- [ ] 实现手动刷新
- [ ] 实现增量更新优化
- [ ] 实现冲突处理
- [ ] 编写刷新单元测试

### 8.5 第五阶段：UI 实现（3-4天）
- [ ] 实现会话列表页面
- [ ] 实现 Dashboard 统计
- [ ] 实现筛选和搜索 UI
- [ ] 实现标记对话框
- [ ] 实现桌面通知
- [ ] 编写 UI 集成测试

### 8.6 第六阶段：集成与测试（2-3天）
- [ ] 端到端流程测试
- [ ] 多 Agent 并发测试
- [ ] 性能测试（大量会话）
- [ ] 用户体验优化
- [ ] 文档完善

**总计：11-17 个工作日**

## 9. 风险与对策

### 9.1 技术风险

| 风险 | 影响 | 概率 | 对策 |
|-----|------|------|------|
| Adapter 状态映射不准确 | 高 | 中 | 明确标识可信度，提供原始状态查看 |
| 并发刷新导致性能问题 | 中 | 中 | 限制并发数，增量更新 |
| 标记丢失 | 中 | 低 | 定期备份，提供恢复机制 |
| 恢复命令失败率高 | 高 | 中 | 提供多种恢复方式，降级策略 |

### 9.2 产品风险

| 风险 | 影响 | 概率 | 对策 |
|-----|------|------|------|
| 系统关注状态误报 | 高 | 中 | 明确标识推导逻辑，允许用户标记忽略 |
| 筛选条件过于复杂 | 中 | 低 | 提供预设筛选，简化操作 |
| 大量会话时性能下降 | 中 | 中 | 分页加载，虚拟滚动 |

---

## 附录：核心模型与依赖

### 核心模型

`AgentSession` 至少包含：Agent/Profile、内部 ID、稳定原生会话 ID、标题、项目或工作目录、运行状态、系统关注状态、当前目标、计划项、最近活动、更新时间、状态来源、可信度、恢复方式和接入等级。

运行状态回答”会话正在做什么”；系统关注状态回答”可信事件是否表明用户需要介入”；`SessionAnnotation` 保存用户主动添加的跟进标记、标签、备注和提醒时间。三个维度分开存储和展示。

`SessionAnnotation` 是 AgentHub 本地持久化数据，以 `Agent/Profile + 原生会话 ID` 关联会话。Adapter 返回的原生会话快照不得覆盖它，原生状态也不能由用户标记反向修改。

### Agent Adapter 会话契约

每个 Adapter 必须实现或明确声明不支持：

- 列出内部会话并读取单个会话。
- 读取原生状态、规划和增量事件。
- 使用稳定原生会话 ID 精确打开或恢复。
- 探测数据源、连接和恢复能力。
- 返回会话发现、状态、规划、事件和恢复的支持等级。

原生 API、Hook、会话文件和 CLI 细节只存在于 Adapter 内，不泄漏到会话服务或 UI。

### 更新流程

1. 从 `agents` 获取已启用 Profile 和 Adapter。
2. Adapter 发现会话、快照和增量事件。
3. 会话服务以 `Agent/Profile + 原生会话 ID` 归一化身份。
4. 映射运行状态，并基于可信事件推导关注状态。
5. 更新读模型、统计和待处理汇总。
6. 合并本地 `SessionAnnotation`，生成系统关注与用户跟进两个筛选维度。
7. 事件驱动用于实时更新，周期扫描保证最终一致，手动刷新作为兜底。

### 精确恢复

恢复入口按 Agent 官方 API、CLI Resume、原生插件或深度链接、原终端/桌面窗口的顺序降级。只有目标明确绑定原生会话 ID 时才算精确恢复；仅激活窗口标记为有限接入。

进程和窗口探测只用于确认 Agent 是否启动、辅助诊断异常退出，或在原生恢复失败时激活窗口，不能单独判断会话完成或待处理状态。

### 与 Workflows 的关系

Sessions 提供稳定会话身份、归一化事件和精确恢复 Interface。Workflows 保存任务执行与会话的关联，并消费可信会话事件判断任务是否完成；Sessions 不保存队列顺序，也不触发下一任务。

### 当前实现

- `src/agent_hub/sessions/models.py`：会话、状态、规划、事件与统计模型。
- `src/agent_hub/sessions/hub.py`：会话聚合、统计、待处理和精确恢复 Interface。
- `src/agent_hub/sessions/adapters/`：会话发现、接入探测与精确恢复 seam。
- `src/agent_hub/sessions/events.py`：当前内存事件记录实现。
- `src/agent_hub/demo/seed.py`：仅供 Mock 演示使用的数据，不属于生产事实来源。
- `src/agent_hub/demo/controller.py`：编排 Mock 状态推进；该能力不进入通用 Session Adapter 契约。

### OpenCode 映射

`OpenCodeSessionAdapter` 使用官方 Server API，并以 `Agent Profile ID + 原生会话 ID` 生成稳定内部身份。工作目录来自 OpenCode `location.directory`，项目名只取该目录名称；Todo 和最近消息文本均读取原生响应，不生成推测步骤。

- `running` 或 `busy` 映射为 `executing`。
- `retry` 保留原生重试消息并映射为 `executing`。
- `idle` 映射为 `unknown`，原因中保留原生 idle，不推断为等待输入或已完成。
- 不在活动结果中的历史会话标记为 `unknown`，原因中保留 inactive，不推断为已关闭。

精确恢复使用 `opencode attach <endpoint> --session <native_session_id> --dir <directory>`。认证通过进程环境变量传入，不出现在命令行、API 响应或事件记录中。

### Codex 映射

`CodexSessionAdapter` 只读 Codex Desktop 本地状态，不要求 API Key、ChatGPT 登录信息或额外 Server。稳定任务元数据来自 `CODEX_HOME` 中版本号最大的 `state_*.sqlite` 的 `threads` 表，轮次状态、规划和最近活动来自每个任务的 `rollout-*.jsonl`。

- 最近生命周期事件为 `task_started`，且没有后续完成或中断事件时映射为 `executing`；由于异常退出可能来不及写入终止事件，该状态可信度为中等。
- 当前轮次存在尚未返回的 `request_user_input` 调用时映射为 `waiting_input`。
- `task_complete` 映射为 `closed`，只表示当前轮次已结束，任务仍可继续发送后续内容。
- `turn_aborted` 映射为 `interrupted`。
- rollout 缺失、损坏或尾部没有完整生命周期证据时映射为 `unknown`，不根据窗口、进程或更新时间推断完成。

规划只读取当前轮次最近一次 `update_plan` 的原生参数。精确定位使用 Codex Desktop 注册的 `codex://threads/<native_thread_id>` 深链；深链包含稳定原生 Thread ID，不依赖窗口标题或最近任务。

当前接入采用周期扫描，不声明 Codex App Server 内存事件流能力。等待授权状态主要存在于 App Server 运行时通知，尚未找到可供 AgentHub 独立进程稳定读取的持久化证据，因此首版不推断 `waiting_permission`。

### OpenCode Desktop 映射

`OpenCodeDesktopSessionAdapter` 不连接 Desktop 内置 HTTP Server，因此不需要读取其每次启动随机生成的认证密码。Adapter 以只读方式打开 `~/.local/share/opencode/opencode.db`，读取顶层 `session`、`message`、`part` 和 `todo`，并使用 `Agent Profile ID + 原生会话 ID` 生成稳定内部身份。

- 会话已归档时映射为 `closed`。
- 最近 assistant 消息没有完成时间时映射为 `executing`。
- 最近响应包含原生 `error` 时映射为 `interrupted`，并保留错误类型。
- 最近消息来自用户且尚未观察到 assistant 完成事件时映射为 `executing`，可信度为中等。
- 最近 assistant 响应已结束但会话未归档时映射为 `unknown`，不根据回复文字或 Todo 猜测任务已经完成。

Todo 状态按原生 `completed/in_progress/pending/cancelled` 映射。恢复入口使用共享同一会话数据库的官方命令 `opencode <directory> --session <native_session_id>`；该入口精确携带原生 ID，但当前打开的是 CLI/TUI，不冒充 OpenCode Desktop 深链。

Dashboard API 在一次刷新中只扫描一次所有 Adapter，再同时生成统计、待处理和会话列表。单个 Adapter 读取失败会记录事件并将对应 Profile 标为断开，不影响其他 Profile 的会话返回。

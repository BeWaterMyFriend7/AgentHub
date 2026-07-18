# AgentHub 领域语言

AgentHub 是本地 AI Agent 管理中枢，统一呈现内部会话和可复用能力，并把操作委托给对应 Agent 的原生能力。

## Agent 与会话

**Agent 类型（Agent Type）**：
一种受支持的 AI Agent 产品，例如 Codex、Claude Code 或 OpenCode。
_避免使用_：工具、客户端

**Agent 安装（Agent Installation）**：
当前操作系统中可被 AgentHub 识别的一份 Agent 安装。
_避免使用_：Agent 实例、应用实例

**Agent 配置（Agent Profile）**：
AgentHub 中描述某个 Agent 安装及其会话、能力接入位置的一组本地配置。
_避免使用_：工具配置、连接配置

**内部会话（Agent Session）**：
由 Agent 原生会话标识唯一确定、可以独立查看状态并精确恢复的一次工作上下文。
_避免使用_：窗口、进程、任务

**待处理会话（Attention Session）**：
处于等待授权、等待输入、等待验收或执行中断状态，需要用户回到原生 Agent 处理的内部会话。
_避免使用_：异常会话、未读会话

**会话接入等级（Session Integration Level）**：
AgentHub 对一个 Agent 的内部会话能够达到的接入程度，分为完整接入、部分接入和有限接入；只检测到进程或窗口属于有限接入。
_避免使用_：会话支持等级、完整支持

## 能力

**能力（Capability）**：
可以被一个或多个 Agent 使用的 Skill、MCP Server 或 Agent 插件。
_避免使用_：资源、组件、工具

**Skill**：
以 Skill 规范描述、向 Agent 提供专业知识或工作流程的能力。

**MCP Server**：
通过 Model Context Protocol 向 Agent 暴露工具、资源或提示的能力。
_避免使用_：MCP 工具

**Agent 插件（Agent Plugin）**：
由 Agent 原生插件机制识别的能力包，可以包含 Skill、MCP Server、App 或其他 Agent 扩展。
_避免使用_：编辑器扩展、浏览器插件、通用软件插件

**能力来源（Capability Source）**：
能力内容的唯一真实来源；多个 Agent 中的安装可以引用同一来源。
_避免使用_：主副本、中央副本

**能力安装（Capability Installation）**：
某个能力在一个 Agent 配置中的可发现实例，拥有独立的状态、兼容性和来源关系。
_避免使用_：能力副本、Agent 能力

**共享安装（Shared Installation）**：
引用统一能力来源、没有独立内容副本的能力安装。
_避免使用_：已复制、已同步

**卸载能力安装（Uninstall Installation）**：
从一个 Agent 配置中移除能力安装，但保留能力来源和其他 Agent 中的安装。
_避免使用_：删除能力、完全卸载

**删除能力来源（Delete Capability Source）**：
删除能力的唯一真实来源，使所有引用该来源的共享安装同时失效或被移除。
_避免使用_：卸载来源、取消共享

**永久清除（Permanent Purge）**：
在能力来源已经删除后，继续删除其恢复备份，使内容无法通过 AgentHub 恢复。
_避免使用_：删除来源、普通卸载

**插件所有权（Plugin Ownership）**：
Agent 插件与其独占安装内容之间的生命周期关系；被其他插件引用的内容不属于独占内容。
_避免使用_：文件归属

## 操作结果

**完整支持（Full Support）**：
一种能力在至少两个 Agent 中通过发现、状态识别以及确定性的启用和停用验收。
_避免使用_：已接入、可用

**原生加载（Native Activation）**：
目标 Agent 已经识别并能够使用某个能力安装，而不只是对应文件存在。
_避免使用_：链接成功、安装完成

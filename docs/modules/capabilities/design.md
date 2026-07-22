# Capabilities 模块设计

## 模块边界

Capabilities 负责回答“有哪些能力、来自哪里、安装到哪些 Agent、是否兼容和是否被原生加载”。创建链接、改配置、卸载或删除等有副作用的动作统一交给 `operations`。

Skill、MCP Server 和 Agent 插件是同一公共模型下的三种能力类型，不拆成三个顶层模块。类型专属的解析器、Adapter 和生命周期策略作为本模块内部组件存在。

## 核心模型

- `Capability`：逻辑能力，包含类型、稳定标识、显示信息和兼容性。
- `CapabilitySource`：内容的真实来源、Manifest 标识和内容指纹。
- `CapabilityInstallation`：某能力在某 Agent/Profile 中的可发现安装。
- `SharedInstallation`：通过目录链接引用来源的安装。
- `NativeLoadState`：Agent 是否已经注册、刷新并实际加载该能力。
- `PluginOwnership`：插件与其内含 Skill、MCP 配置之间的所有权和引用关系。

同名能力不能只按名称合并，应结合能力类型、Manifest 标识、来源和内容指纹识别。文件系统和 Agent 原生配置是事实来源，数据库保存归一化索引、快照和审计引用。

## 发现流程

1. 从 `agents` 获取已启用 Profile 和能力支持声明。
2. Agent Adapter 给出原生发现位置、配置格式和注册方式。
3. 类型扫描器解析真实目录、链接、Manifest、内容指纹、配置和健康信息。
4. 清单服务按稳定能力身份聚合来源和安装。
5. 生成 Skill/MCP/插件 × Agent 状态矩阵。
6. 原生加载结果独立于文件分发结果；链接存在但未加载时标记“已分发但未原生加载”。

## 公共安装状态

来源、共享安装、本地副本、缺失、冲突、断链、无效、未兼容、已分发但未原生加载、健康检查失败。

## 类型策略

- Skill：解析 `SKILL.md`、兼容性和内容指纹，支持按单个 Skill 聚合与共享。
- MCP Server：归一化传输方式、命令或端点、Tools/Resources/Prompts 和健康状态；敏感值不进入公共模型。
- Agent 插件：解析原生 Manifest/Catalog、版本、更新和内含能力，并维护所有权关系。

历史 SkillBridge 设计仅作为 [`references/`](./references/) 中的追溯材料，旧源码的处理结论见[逐文件迁移记录](./references/skill-bridge-migration.md)。三种类型出现足够多的独立模型和流程后，再考虑拆分专属设计文档。

## 当前实现

- `src/agent_hub/capabilities/models.py`：统一能力、来源、Agent 安装、目录状态和原生加载状态模型。
- `src/agent_hub/capabilities/inventory.py`：通过一次 `discover` 完成 Skill Manifest 解析、内容指纹、来源推断、同名多来源拆分和 Agent 状态矩阵聚合。来源 ID 由来源路径稳定标识，内容版本只进入 fingerprint。
- `src/agent_hub/platform/links.py`：为扫描提供目录、目录链接、断链和无效路径的统一识别。

当前只迁移 Skill 的只读发现与状态聚合。MCP Server、Agent 插件、原生加载验证、HTTP API 与 UI 仍属于后续功能，不以公共模型已经存在为完成证据。

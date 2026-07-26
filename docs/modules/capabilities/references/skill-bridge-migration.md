# SkillBridge 迁移记录

> 状态：历史实现迁移记录，不是当前需求或设计事实来源。当前产品范围以 [`docs/README.md`](../../../README.md) 为准，模块边界以 [Capabilities 需求](../requirements.md)和 [Operations 需求](../../operations/requirements.md)为准。

## 结论

SkillBridge 不再作为独立应用运行，也不在 `src/` 中保留第二套 FastAPI、SQLite、模板和平台实现。可复用的领域能力已迁入 AgentHub；尚未实现的能力只保留业务意图和验收边界，后续基于统一模型重新设计，不直接复制旧代码。

完整旧实现可从 Git 历史恢复。本记录用于回答旧文件去了哪里、哪些能力已经完成迁移、哪些需求仍待实现。

## 逐文件处理清单

| 历史文件 | 处理方式 |
| --- | --- |
| `src/skill_bridge/README.md` | 删除；有效说明由本文、模块需求和模块设计承接 |
| `src/skill_bridge/main.py` | 删除；不再保留独立应用入口和端口 |
| `src/skill_bridge/requirements.txt` | 删除；依赖统一由仓库根目录管理 |
| `src/skill_bridge/skillbridge/__init__.py` | 随旧 Python 包删除，不建立兼容导入 |
| `src/skill_bridge/skillbridge/catalog.py` | 领域逻辑迁入 `agent_hub/capabilities` |
| `src/skill_bridge/skillbridge/config.py` | 应用常量删除；Agent 路径配置改由 Profile/Adapter 提供 |
| `src/skill_bridge/skillbridge/database.py` | 不复制；Agent 配置、来源选择和审计分别进入新的持久化边界 |
| `src/skill_bridge/skillbridge/models.py` | Skill 状态模型迁入统一 Capability 模型；旧 API 输入模型删除 |
| `src/skill_bridge/skillbridge/platform/__init__.py` | 随 Windows 专用平台包删除 |
| `src/skill_bridge/skillbridge/platform/windows.py` | 目录链接能力迁入跨平台 `agent_hub/platform/links.py` |
| `src/skill_bridge/skillbridge/routes.py` | 不复制；有效业务入口后续接入唯一 AgentHub API/UI |
| `src/skill_bridge/skillbridge/scanner.py` | 扫描、Manifest 解析和指纹迁入 `agent_hub/capabilities/inventory.py` |
| `src/skill_bridge/skillbridge/security.py` | 路径安全迁入 Operations/Platform；会话令牌按统一应用安全边界重设 |
| `src/skill_bridge/skillbridge/sharing.py` | 共享、备份和回滚迁入 Operations；来源迁移重新实现 |
| `src/skill_bridge/skillbridge/static/style.css` | 删除；旧应用样式不进入统一 UI |
| `src/skill_bridge/skillbridge/templates/base.html` | 删除；旧独立应用页面框架不迁移 |
| `src/skill_bridge/skillbridge/templates/index.html` | 删除；状态矩阵交互仅作为历史需求参考 |
| `src/skill_bridge/skillbridge/templates/logs.html` | 删除；审计展示后续由统一 UI 基于新审计模型实现 |
| `src/skill_bridge/skillbridge/templates/settings.html` | 删除；Agent 配置后续由统一 Profile 页面实现 |
| `src/skill_bridge/skillbridge/templates/skill_detail.html` | 删除；能力详情后续由统一 Capability 读模型驱动 |
| `docs/guides/skill-bridge-operations.md` | 删除；旧应用不可启动，历史信息改由需求来源和本文追溯 |

## 已完成迁移

| SkillBridge 文件或职责 | AgentHub 去向 | 处理结论 |
| --- | --- | --- |
| `scanner.py`：扫描 Skill、解析 `SKILL.md`、生成内容指纹 | `src/agent_hub/capabilities/inventory.py` | 已迁移；以文件系统为事实来源，并统一使用 SHA-256 指纹 |
| `catalog.py`：来源推断、状态聚合、Skill × Agent 矩阵 | `src/agent_hub/capabilities/` | 已迁移；增加稳定来源身份和同名多来源拆分 |
| `models.py` 中的 Skill 状态模型 | `src/agent_hub/capabilities/models.py` | 已迁移到统一 Capability、Source、Installation 模型 |
| `sharing.py` 的启用共享、停用共享、备份和回滚 | `src/agent_hub/operations/` | 已迁移；增加计划、预检、确认后复检、逐步审计和失败补偿 |
| `platform/windows.py` 的 Junction 创建、解析、验证和移除 | `src/agent_hub/platform/links.py` | 已迁移；同时支持 Windows Junction 与 macOS/Linux Symbolic Link |
| `security.py` 的路径边界检查 | `src/agent_hub/operations/manager.py` 与 `src/agent_hub/platform/links.py` | 已迁移并收紧；同时检查词法路径和物理解析路径，保护根目录不可操作 |

## 保留需求、重新实现

| 旧实现 | 后续归属 | 不直接复制的原因 |
| --- | --- | --- |
| `database.py` 的 Agent 配置 | `agents` 持久化 Repository | Agent 类型、安装和 Profile 已拆分，旧表结构无法表达多 Profile 和 Adapter 能力 |
| `database.py` 的来源选择 | `capabilities` 持久化 Repository | 旧实现只按 `skill_name` 保存，会错误合并同名不同来源；新实现必须使用稳定 `capability_id` 或 `source_id` |
| `database.py` 的操作日志 | `operations` 持久化 Audit Adapter | 旧记录缺少操作者、完整步骤结果、前后状态和人工恢复信息 |
| `sharing.py:migrate_source()` | `operations` 来源迁移操作 | 旧实现先更新来源选择、再逐个重建链接，部分失败仍可能返回成功，缺少原子补偿和完整审计 |
| `routes.py` 的批量共享接口 | AgentHub 应用服务层 | 批量请求需要拆成独立可审计子操作，不能绕过单项预检和确认 |
| `routes.py` 的目录浏览和 Windows 文件夹选择器 | 统一桌面基础设施 | 旧实现仅适用于 Windows；目标产品必须兼容 Windows、macOS、Linux |
| `routes.py` 的会话令牌中间件 | AgentHub 本地 API 安全边界 | 是否采用令牌、防跨站或桌面进程通道需结合唯一应用部署方式统一设计 |
| `templates/` 与 `static/` 的交互 | AgentHub 统一 UI | 页面属于旧独立应用，不能与当前 UI 并存；状态矩阵和影响确认交互可作为历史原型参考 |

## 不迁移

| 文件或能力 | 处理结论 |
| --- | --- |
| `main.py`、独立 FastAPI 应用和端口 `17890` | 删除；AgentHub 只保留一个应用入口 |
| `requirements.txt` | 删除；依赖统一由仓库根目录管理 |
| `config.py` 中的默认 Agent 路径 | 删除；真实路径由 Agent Profile 与 Adapter 发现提供 |
| `scan_cache` | 不迁移为事实来源；如未来需要性能缓存，必须可丢弃并由真实文件系统重建 |
| SkillBridge 操作手册 | 删除；旧应用不可再启动，避免形成错误操作入口 |

## 后续验收要求

- Agent Profile、来源选择和操作审计通过明确 Repository/Adapter 持久化，不让数据库模型反向定义领域模型。
- 来源迁移必须执行影响分析、全量预检、独立确认、逐步审计和失败补偿，完成后重新扫描事实来源。
- 批量操作必须返回每个能力和 Agent 的独立结果；单项失败不能被整体“成功”掩盖。
- 能力管理 UI、API 和目录选择全部进入唯一 AgentHub 应用，并提供 Windows、macOS、Linux 的一致边界。

## 追溯方式

- 领域逻辑提取提交：`589b83e refactor: 提取 capabilities 与 operations 模块`
- 历史需求来源：[Skill 管理需求 v1.0](./skill-management-v1.0.md)
- 实现历史与验证：[Capabilities 模块拆分记录](./2026-07-22-capabilities-module-split.md)与 [Windows 文件系统操作验证](../../operations/verification/2026-07-22-windows-filesystem-operations.md)
